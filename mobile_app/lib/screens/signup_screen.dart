import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../widgets/app_logo.dart';
import '../widgets/google_logo.dart';

class SignupScreen extends StatefulWidget {
  final String? initialEmail;
  final String? initialPhone;
  final String? initialName;

  const SignupScreen({
    super.key,
    this.initialEmail,
    this.initialPhone,
    this.initialName,
  });

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final _formKey = GlobalKey<FormState>();
  final AuthService _authService = AuthService();

  late TextEditingController _nameController;
  late TextEditingController _emailController;
  late TextEditingController _phoneController;
  final TextEditingController _smsCodeController = TextEditingController();

  bool _isLoading = false;
  bool _authenticated = false;
  bool _phoneCodeSent = false;
  String _verificationId = '';
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    final currentUser = _authService.currentUser;
    if (currentUser != null) {
      _authenticated = true;
      final email = (widget.initialEmail?.isNotEmpty == true)
          ? widget.initialEmail!
          : (currentUser.email ?? '');
      final name = (currentUser.displayName?.isNotEmpty == true)
          ? currentUser.displayName!
          : (widget.initialName ?? '');
      final phone = (widget.initialPhone?.isNotEmpty == true)
          ? widget.initialPhone!
          : (currentUser.phoneNumber ?? '');

      _nameController = TextEditingController(text: name);
      _emailController = TextEditingController(text: email);
      _phoneController = TextEditingController(text: phone);
    } else {
      _nameController = TextEditingController(text: widget.initialName);
      _emailController = TextEditingController(text: widget.initialEmail);
      _phoneController = TextEditingController(text: widget.initialPhone);
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _smsCodeController.dispose();
    super.dispose();
  }

  /// Triggers Google Sign-In for verification
  Future<void> _verifyWithGoogle() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final result = await _authService.loginWithGoogle();

    setState(() {
      _isLoading = false;
    });

    if (result['success'] == true) {
      // User is authenticated in Firebase Auth
      final user = _authService.currentUser;
      if (user != null) {
        setState(() {
          _authenticated = true;
          _emailController.text = user.email ?? '';
          _nameController.text = user.displayName ?? '';
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Google account authenticated. Complete profile registration.')),
          );
        }
      }
    } else {
      // If code is ACCOUNT_NOT_FOUND, that is actually expected during Signup!
      // It means the user is authenticated in Firebase Auth, but not in Firestore.
      if (result['code'] == 'ACCOUNT_NOT_FOUND') {
        final googleUser = _authService.currentUser;
        setState(() {
          _authenticated = true;
          _emailController.text = (result['email'] as String?)?.isNotEmpty == true
              ? (result['email'] as String)
              : (googleUser?.email ?? '');
          _nameController.text = (googleUser?.displayName?.isNotEmpty == true)
              ? googleUser!.displayName!
              : (result['name'] as String? ?? '');
        });
      } else {
        setState(() {
          _errorMessage = result['message'] as String?;
        });
      }
    }
  }

  /// Sends Phone SMS code for verification
  Future<void> _verifySendPhoneCode() async {
    final phone = _phoneController.text.trim();
    if (phone.isEmpty) {
      setState(() {
        _errorMessage = 'Please enter your phone number first.';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    await _authService.verifyPhone(
      phoneNumber: phone,
      onCodeSent: (verificationId) {
        setState(() {
          _isLoading = false;
          _phoneCodeSent = true;
          _verificationId = verificationId;
        });
      },
      onError: (error) {
        setState(() {
          _isLoading = false;
          _errorMessage = error;
        });
      },
    );
  }

  /// Verifies Phone Code and marks authenticated
  Future<void> _verifyPhoneCode() async {
    final code = _smsCodeController.text.trim();
    if (code.isEmpty || code.length < 6) {
      setState(() {
        _errorMessage = 'Please enter the 6-digit code.';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final result = await _authService.loginWithPhoneCode(_verificationId, code);

    setState(() {
      _isLoading = false;
    });

    if (result['success'] == true) {
      // User exists in Firestore (should not happen on signup, but let's check)
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Account already exists! Please go back and log in.')),
        );
        Navigator.of(context).pop();
      }
    } else {
      if (result['code'] == 'ACCOUNT_NOT_FOUND') {
        setState(() {
          _authenticated = true;
          _phoneController.text = result['phone'] as String? ?? _phoneController.text;
        });
      } else {
        setState(() {
          _errorMessage = result['message'] as String?;
        });
      }
    }
  }

  /// Registers user profile in Firestore
  Future<void> _handleSignup() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final name = _nameController.text.trim();
    final email = _emailController.text.trim();
    final phone = _phoneController.text.trim();

    final result = await _authService.signup(
      name,
      email,
      phone: phone.isNotEmpty ? phone : null,
    );

    setState(() {
      _isLoading = false;
    });

    if (result['success'] == true) {
      if (mounted) {
        _showSuccessDialog();
      }
    } else {
      setState(() {
        _errorMessage = result['message'] as String;
      });
    }
  }

  /// Displays success dialog after registration
  void _showSuccessDialog() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return AlertDialog(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16.0),
          ),
          title: const Row(
            children: [
              Icon(Icons.check_circle_outline, color: Colors.green, size: 28),
              SizedBox(width: 10),
              Text(
                'Registration Success',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
            ],
          ),
          content: const Text(
            'Your profile has been registered in the database. '
            'Please log in using your credentials to access the application.',
            style: TextStyle(fontSize: 14, height: 1.4),
          ),
          actions: [
            ElevatedButton(
              onPressed: () {
                Navigator.of(context).pop(); // Close success dialog
                Navigator.of(context).pop(); // Go back to login screen
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: Theme.of(context).primaryColor,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
              child: const Text('OK'),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Colors.grey.shade50,
      appBar: AppBar(
        title: const Text('Register Profile', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.black87,
        elevation: 0,
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32.0),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Center(child: AppLogo(size: 72)),
                const SizedBox(height: 20),

                const Text(
                  'Create Database Profile',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: Colors.black87,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Verify via Google or Phone first, then set display name.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 13,
                    color: Colors.black54,
                  ),
                ),
                const SizedBox(height: 24),

                // Error Alert Box
                if (_errorMessage != null) ...[
                  Container(
                    padding: const EdgeInsets.symmetric(vertical: 10.0, horizontal: 16.0),
                    decoration: BoxDecoration(
                      color: Colors.red.shade50,
                      borderRadius: BorderRadius.circular(10.0),
                      border: Border.all(color: Colors.red.shade200),
                    ),
                    child: Text(
                      _errorMessage!,
                      style: TextStyle(color: Colors.red.shade800, fontSize: 13),
                      textAlign: TextAlign.center,
                    ),
                  ),
                  const SizedBox(height: 20),
                ],

                // Step 1: Authentication Verification Panel
                if (!_authenticated) ...[
                  Card(
                    elevation: 1,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const Text(
                            'Step 1: Choose verification method',
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                          ),
                          const SizedBox(height: 16),

                          // Verify via Google button
                          _isLoading
                              ? const Center(child: CircularProgressIndicator())
                              : OutlinedButton.icon(
                                  onPressed: _verifyWithGoogle,
                                  icon: const GoogleLogo(size: 18),
                                  label: const Text('Verify Google Account', style: TextStyle(fontWeight: FontWeight.bold)),
                                  style: OutlinedButton.styleFrom(
                                    padding: const EdgeInsets.symmetric(vertical: 12),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                                  ),
                                ),
                          const SizedBox(height: 12),
                          const Center(child: Text('OR', style: TextStyle(fontSize: 11, color: Colors.grey))),
                          const SizedBox(height: 12),

                          // Verify via Phone SMS
                          if (!_phoneCodeSent) ...[
                            TextFormField(
                              controller: _phoneController,
                              keyboardType: TextInputType.phone,
                              maxLength: 10,
                              decoration: InputDecoration(
                                labelText: 'Mobile Number',
                                hintText: '9876543210',
                                counterText: '',
                                prefixIcon: const Padding(
                                  padding: EdgeInsets.symmetric(horizontal: 12.0),
                                  child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(Icons.phone_outlined, size: 20, color: Colors.black54),
                                      SizedBox(width: 6),
                                      Text('🇮🇳', style: TextStyle(fontSize: 18)),
                                      SizedBox(width: 4),
                                      Text(
                                        '+91 ',
                                        style: TextStyle(
                                          fontWeight: FontWeight.bold,
                                          fontSize: 15,
                                          color: Colors.black87,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                              ),
                            ),
                            const SizedBox(height: 10),
                            _isLoading
                                ? const Center(child: CircularProgressIndicator())
                                : ElevatedButton(
                                    onPressed: _verifySendPhoneCode,
                                    child: const Text('Verify via SMS'),
                                  ),
                          ] else ...[
                            TextFormField(
                              controller: _smsCodeController,
                              keyboardType: TextInputType.number,
                              decoration: InputDecoration(
                                labelText: '6-digit SMS Code',
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                              ),
                            ),
                            const SizedBox(height: 10),
                            _isLoading
                                ? const Center(child: CircularProgressIndicator())
                                : Row(
                                    children: [
                                      Expanded(
                                        child: OutlinedButton(
                                          onPressed: () {
                                            setState(() {
                                              _phoneCodeSent = false;
                                              _smsCodeController.clear();
                                            });
                                          },
                                          child: const Text('Back'),
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Expanded(
                                        flex: 2,
                                        child: ElevatedButton(
                                          onPressed: _verifyPhoneCode,
                                          child: const Text('Confirm Code'),
                                        ),
                                      ),
                                    ],
                                  ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ] else ...[
                  // Step 2: User profile fields (Visible only when authenticated)
                  Card(
                    elevation: 1,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    child: Padding(
                      padding: const EdgeInsets.all(18.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const Row(
                            children: [
                              Icon(Icons.verified, color: Colors.green, size: 20),
                              SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  'Step 2: Complete profile registration',
                                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 20),

                          // Full Name
                          TextFormField(
                            controller: _nameController,
                            keyboardType: TextInputType.name,
                            decoration: InputDecoration(
                              labelText: 'Full Name',
                              prefixIcon: const Icon(Icons.person_outline),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(10.0),
                              ),
                            ),
                            validator: (value) {
                              if (value == null || value.trim().isEmpty) {
                                return 'Please enter your name.';
                              }
                              return null;
                            },
                          ),
                          const SizedBox(height: 16),

                          // Locked Email field (Visible only if signed up via Google)
                          if (_emailController.text.isNotEmpty) ...[
                            TextFormField(
                              controller: _emailController,
                              readOnly: true,
                              decoration: InputDecoration(
                                labelText: 'Google Email (Verified)',
                                prefixIcon: const Icon(Icons.mail_outline),
                                suffixIcon: const Icon(Icons.lock_outline, size: 18),
                                fillColor: Colors.grey.shade100,
                                filled: true,
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10.0),
                                ),
                              ),
                            ),
                            const SizedBox(height: 16),
                          ],

                          // Locked Phone field (Visible only if signed up via Phone)
                          if (_phoneController.text.isNotEmpty) ...[
                            TextFormField(
                              controller: _phoneController,
                              readOnly: true,
                              decoration: InputDecoration(
                                labelText: 'Phone Number (Verified)',
                                prefixIcon: const Icon(Icons.phone_outlined),
                                suffixIcon: const Icon(Icons.lock_outline, size: 18),
                                fillColor: Colors.grey.shade100,
                                filled: true,
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10.0),
                                ),
                              ),
                            ),
                            const SizedBox(height: 16),
                          ],
                          const SizedBox(height: 24),

                          // Signup Submit Button
                          _isLoading
                              ? const Center(child: CircularProgressIndicator())
                              : ElevatedButton(
                                  onPressed: _handleSignup,
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: theme.primaryColor,
                                    foregroundColor: Colors.white,
                                    padding: const EdgeInsets.symmetric(vertical: 14.0),
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(10.0),
                                    ),
                                  ),
                                  child: const Text(
                                    'Register Account',
                                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                                  ),
                                ),
                          const SizedBox(height: 12),
                          TextButton(
                            onPressed: () {
                              setState(() {
                                _authenticated = false;
                                _emailController.clear();
                                _phoneController.clear();
                                _nameController.clear();
                              });
                            },
                            child: const Text('Reset verification method'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],

                const SizedBox(height: 24),
                // Back to Login Link
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text('Already registered? ', style: TextStyle(color: Colors.black54)),
                    GestureDetector(
                      onTap: () {
                        Navigator.of(context).pop();
                      },
                      child: Text(
                        'Sign In',
                        style: TextStyle(
                          color: theme.primaryColor,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
