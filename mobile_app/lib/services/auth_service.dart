import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter/foundation.dart' show kIsWeb, debugPrint;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'api_service.dart';

class AuthService {
  static const String _keyIsLoggedIn = 'auth_is_logged_in';
  static const String _keyUserEmail = 'auth_user_email';
  static const String _keyUserName = 'auth_user_name';
  static const String _keyOnboardingComplete = 'auth_onboarding_complete';

  static const String _webClientId =
      '1063410976132-oiq963qr654635lt75hn7dasp9cg8r7j.apps.googleusercontent.com';
  static final Map<String, String> _verificationToPhone = {};
  static Future<void>? _googleSignInInitFuture;

  final FirebaseAuth _auth = FirebaseAuth.instance;

  User? get currentUser => _auth.currentUser;

  AuthService();

  Future<void> _ensureGoogleSignInInitialized() {
    return _googleSignInInitFuture ??= GoogleSignIn.instance.initialize(
      serverClientId: _webClientId,
    );
  }

  String _googleSignInFailureMessage(Object? error) {
    if (error is GoogleSignInException) {
      switch (error.code) {
        case GoogleSignInExceptionCode.canceled:
          return 'Google Sign-In prompt was closed. Please try again.';
        case GoogleSignInExceptionCode.interrupted:
          return 'Google Sign-In was interrupted. Please try again once.';
        case GoogleSignInExceptionCode.clientConfigurationError:
          return 'Google Sign-In is not configured for this APK. Add this APK signing SHA-1/SHA-256 to Firebase, download the updated google-services.json, rebuild, and reinstall.';
        case GoogleSignInExceptionCode.providerConfigurationError:
          return 'Google Sign-In provider is not enabled/configured in Firebase. Enable Google provider in Firebase Authentication and try again.';
        case GoogleSignInExceptionCode.uiUnavailable:
          return 'Google Sign-In UI is unavailable on this device. Please update Google Play services and try again.';
        case GoogleSignInExceptionCode.userMismatch:
          return 'Google returned a different account than expected. Please sign out of Google in the app and try again.';
        case GoogleSignInExceptionCode.unknownError:
          return error.description?.isNotEmpty == true
              ? 'Google Sign-In error: ${error.description}'
              : 'Google Sign-In failed unexpectedly. Please try again.';
      }
    }

    final errorText = error?.toString() ?? '';
    final lowerErrorText = errorText.toLowerCase();

    if (lowerErrorText.contains('clientconfigurationerror') ||
        lowerErrorText.contains('api_exception: 10') ||
        lowerErrorText.contains('apiexception: 10') ||
        lowerErrorText.contains('developer_error') ||
        lowerErrorText.contains('oauth client')) {
      return 'Google Sign-In is not configured for this APK. Add this APK signing SHA-1/SHA-256 to Firebase, download the updated google-services.json, rebuild, and reinstall.';
    }

    if (errorText.isEmpty || lowerErrorText.contains('canceled')) {
      return 'Google Sign-In prompt was closed. Please try again.';
    }

    if (lowerErrorText.contains('interrupted')) {
      return 'Google Sign-In was interrupted. Please try again once.';
    }

    if (lowerErrorText.contains('firebase_auth') ||
        lowerErrorText.contains('invalid-credential') ||
        lowerErrorText.contains('invalid credential')) {
      return 'Firebase rejected the Google credential. Recheck the Firebase Android app SHA-1/SHA-256 and the Google provider settings, then rebuild with the updated google-services.json.';
    }

    if (lowerErrorText.contains('network')) {
      return 'Could not reach Google Sign-In. Please check your internet connection and try again.';
    }

    return 'Google Sign-In error: $errorText';
  }

  /// Check onboarding completed state.
  Future<bool> isOnboardingComplete() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_keyOnboardingComplete) ?? false;
  }

  /// Mark onboarding completed.
  Future<void> setOnboardingComplete() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyOnboardingComplete, true);
  }

  /// Check user login session.
  Future<bool> isLoggedIn() async {
    final prefs = await SharedPreferences.getInstance();
    final localLoggedIn = prefs.getBool(_keyIsLoggedIn) ?? false;
    return localLoggedIn && _auth.currentUser != null;
  }

  /// Get current user display name.
  Future<String> getUserName() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyUserName) ?? 'User';
  }

  /// Get current user email.
  Future<String> getUserEmail() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyUserEmail) ?? 'user@example.com';
  }

  /// Google OAuth sign-in calling Firebase Auth & Firestore.
  Future<Map<String, dynamic>> loginWithGoogle() async {
    try {
      UserCredential? userCredential;
      String? googleEmail;
      String? googleName;

      if (kIsWeb) {
        final GoogleAuthProvider authProvider = GoogleAuthProvider();
        userCredential = await _auth.signInWithPopup(authProvider);
        if (userCredential.user != null) {
          googleEmail = userCredential.user!.email;
          googleName = userCredential.user!.displayName;
        }
      } else {
        try {
          await _ensureGoogleSignInInitialized();
        } catch (initErr) {
          debugPrint('Google Sign-In initialize notice: $initErr');
          return {
            'success': false,
            'message': _googleSignInFailureMessage(initErr),
          };
        }

        GoogleSignInAccount googleUser;
        try {
          googleUser = await GoogleSignIn.instance.authenticate();
        } catch (authErr) {
          debugPrint('Google authenticate initial notice: $authErr');
          return {
            'success': false,
            'message': _googleSignInFailureMessage(authErr),
          };
        }

        googleEmail = googleUser.email;
        googleName = googleUser.displayName ?? 'User';

        final GoogleSignInAuthentication googleAuth = googleUser.authentication;
        if (googleAuth.idToken == null) {
          return {
            'success': false,
            'message':
                'Google did not return an ID token. Recheck Firebase Google provider and OAuth client configuration.',
          };
        }

        try {
          final AuthCredential credential = GoogleAuthProvider.credential(
            idToken: googleAuth.idToken,
          );
          userCredential = await _auth.signInWithCredential(credential);
          if (userCredential.user != null) {
            googleEmail = userCredential.user!.email ?? googleEmail;
            googleName = userCredential.user!.displayName ?? googleName;
          }
        } catch (fbErr) {
          debugPrint('Firebase credential signin notice: $fbErr');
          return {
            'success': false,
            'message': _googleSignInFailureMessage(fbErr),
          };
        }
      }

      final emailKey =
          (googleEmail ??
                  _auth.currentUser?.email ??
                  _auth.currentUser?.uid ??
                  'google_user')
              .trim()
              .toLowerCase();

      // Check if user exists in Cloud Firestore
      DocumentSnapshot<Map<String, dynamic>>? doc;
      try {
        doc = await FirebaseFirestore.instance
            .collection('users')
            .doc(emailKey)
            .get();
      } catch (fsErr) {
        debugPrint('Firestore fetch user notice: $fsErr');
      }

      if (doc == null || !doc.exists) {
        return {
          'success': false,
          'code': 'ACCOUNT_NOT_FOUND',
          'message': 'Account not found in our database.',
          'email': googleEmail ?? emailKey,
          'name': googleName ?? 'User',
        };
      }

      // User exists, save local preferences
      final data = doc.data() ?? {};
      final name = data['name'] as String? ?? googleName ?? 'User';

      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_keyIsLoggedIn, true);
      await prefs.setString(_keyUserEmail, emailKey);
      await prefs.setString(_keyUserName, name);

      return {'success': true};
    } catch (e) {
      return {'success': false, 'message': _googleSignInFailureMessage(e)};
    }
  }

  /// Triggers SMS OTP sending via the backend SMS gateway API.
  Future<void> verifyPhone({
    required String phoneNumber,
    required Function(String verificationId) onCodeSent,
    required Function(String error) onError,
  }) async {
    try {
      String cleanDigits = phoneNumber.replaceAll(RegExp(r'\D'), '');
      if (cleanDigits.startsWith('91') && cleanDigits.length == 12) {
        cleanDigits = cleanDigits.substring(2);
      }
      if (cleanDigits.length != 10) {
        onError('Please enter a valid 10-digit Indian mobile number.');
        return;
      }
      String formattedPhone = '+91$cleanDigits';

      // Dispatch backend API request to send SMS OTP using server environment key
      final url = Uri.parse('${ApiService.baseUrl}/sms/send-otp');
      final response = await http
          .post(
            url,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'phone': formattedPhone}),
          )
          .timeout(const Duration(seconds: 60));

      Map<String, dynamic> decoded = {};
      try {
        final body = jsonDecode(response.body);
        if (body is Map<String, dynamic>) {
          decoded = body;
        }
      } catch (_) {}

      if (response.statusCode < 200 ||
          response.statusCode >= 300 ||
          decoded['success'] != true) {
        final message = decoded['message'] ?? decoded['detail'];
        onError(
          message?.toString() ??
              'Unable to send OTP right now. Please try again shortly.',
        );
        return;
      }

      final verificationId =
          (decoded['verification_id'] as String?) ??
          'vid_${DateTime.now().millisecondsSinceEpoch}';
      final verifiedPhone = (decoded['phone'] as String?) ?? formattedPhone;
      _verificationToPhone[verificationId] = verifiedPhone;

      // Signal success to move to OTP code entry screen
      onCodeSent(verificationId);
    } catch (e) {
      debugPrint('Backend SMS OTP endpoint notice: $e');
      onError(
        'Could not contact the OTP server. Please check your connection and try again.',
      );
    }
  }

  /// Verifies SMS OTP code via backend Textbee endpoint and logs in.
  Future<Map<String, dynamic>> loginWithPhoneCode(
    String verificationId,
    String smsCode,
  ) async {
    try {
      final formattedPhone = _verificationToPhone[verificationId] ?? '';
      if (formattedPhone.isEmpty) {
        return {
          'success': false,
          'message':
              'OTP session expired. Please request a new verification code.',
        };
      }

      // 1. Verify OTP with backend Textbee verification endpoint
      final url = Uri.parse('${ApiService.baseUrl}/sms/verify-otp');
      final response = await http
          .post(
            url,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'phone': formattedPhone, 'otp': smsCode.trim()}),
          )
          .timeout(const Duration(seconds: 30));

      Map<String, dynamic> decoded = {};
      try {
        final body = jsonDecode(response.body);
        if (body is Map<String, dynamic>) {
          decoded = body;
        }
      } catch (_) {}

      if (response.statusCode < 200 ||
          response.statusCode >= 300 ||
          decoded['success'] != true) {
        final message = decoded['message'] ?? decoded['detail'];
        return {
          'success': false,
          'message':
              message?.toString() ??
              'Invalid verification OTP code. Please try again.',
        };
      }

      // 3. Ensure active Firebase Auth session for Firestore security rules
      User? user = _auth.currentUser;
      if (user == null) {
        try {
          final cred = await _auth.signInAnonymously();
          user = cred.user;
        } catch (e) {
          debugPrint('Anonymous signin notice: $e');
          user = _auth.currentUser;
        }
      }

      final identifier = formattedPhone.isNotEmpty
          ? formattedPhone
          : (user?.phoneNumber ?? user?.uid ?? 'phone_user');

      // 4. Query Firestore user document
      DocumentSnapshot<Map<String, dynamic>>? doc;
      try {
        doc = await FirebaseFirestore.instance
            .collection('users')
            .doc(identifier)
            .get();
      } catch (fsErr) {
        debugPrint('Firestore fetch user notice: $fsErr');
      }

      if (doc == null || !doc.exists) {
        return {
          'success': false,
          'code': 'ACCOUNT_NOT_FOUND',
          'message': 'Account not found in our database.',
          'phone': identifier,
        };
      }

      final data = doc.data() ?? {};
      final name = data['name'] as String? ?? 'User';
      final email = data['email'] as String? ?? identifier;

      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_keyIsLoggedIn, true);
      await prefs.setString(_keyUserEmail, email);
      await prefs.setString(_keyUserName, name);

      return {'success': true};
    } catch (e) {
      return {'success': false, 'message': 'Phone verification error: $e'};
    }
  }

  /// Signup profile registration in Firestore.
  Future<Map<String, dynamic>> signup(
    String name,
    String email, {
    String? phone,
  }) async {
    try {
      User? user = _auth.currentUser;
      if (user == null) {
        try {
          final cred = await _auth.signInAnonymously();
          user = cred.user;
        } catch (e) {
          debugPrint('Anonymous signin during signup notice: $e');
          user = _auth.currentUser;
        }
      }

      final docKey = email.trim().isNotEmpty
          ? email.trim().toLowerCase()
          : (phone ??
                user?.phoneNumber ??
                user?.uid ??
                'user_${DateTime.now().millisecondsSinceEpoch}');

      // Save profile to Cloud Firestore
      await FirebaseFirestore.instance.collection('users').doc(docKey).set({
        'uid': user?.uid ?? docKey,
        'name': name.trim(),
        'email': email.trim().toLowerCase(),
        'phone': phone ?? user?.phoneNumber ?? '',
        'createdAt': FieldValue.serverTimestamp(),
      });

      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_keyIsLoggedIn, true);
      await prefs.setString(
        _keyUserEmail,
        email.trim().isNotEmpty ? email.trim().toLowerCase() : docKey,
      );
      await prefs.setString(_keyUserName, name.trim());

      return {'success': true};
    } catch (e) {
      return {'success': false, 'message': 'Registration failed: $e'};
    }
  }

  /// Clears user session.
  Future<void> signOut() async {
    try {
      if (!kIsWeb) {
        await GoogleSignIn.instance.signOut();
      }
      await _auth.signOut();

      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_keyIsLoggedIn, false);
      await prefs.remove(_keyUserEmail);
      await prefs.remove(_keyUserName);
    } catch (_) {}
  }

  /// Alias for signOut to match original screen calls.
  Future<void> logout() async {
    await signOut();
  }
}
