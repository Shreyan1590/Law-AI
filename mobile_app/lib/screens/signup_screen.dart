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

class _SignupScreenState extends State<SignupScreen>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final AuthService _authService = AuthService();

  late TextEditingController _nameController;
  late TextEditingController _emailController;
  late TextEditingController _phoneController;
  final TextEditingController _smsCodeController = TextEditingController();

  late TabController _tabController;
  late AnimationController _pulseController;
  late Animation<double> _scaleAnimation;

  bool _isLoading = false;
  bool _authenticated = false;
  bool _phoneCodeSent = false;
  String _verificationId = '';
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);

    _scaleAnimation = Tween<double>(begin: 0.98, end: 1.02).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    if (widget.initialEmail?.isNotEmpty == true || widget.initialPhone?.isNotEmpty == true) {
      _authenticated = true;
      _nameController = TextEditingController(text: widget.initialName ?? '');
      _emailController = TextEditingController(text: widget.initialEmail ?? '');
      _phoneController = TextEditingController(text: widget.initialPhone ?? '');
    } else {
      _authenticated = false;
      _nameController = TextEditingController(text: widget.initialName ?? '');
      _emailController = TextEditingController(text: widget.initialEmail ?? '');
      _phoneController = TextEditingController(text: widget.initialPhone ?? '');
    }
  }

  @override
  void dispose() {
    _tabController.dispose();
    _pulseController.dispose();
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
      final user = _authService.currentUser;
      if (user != null) {
        setState(() {
          _authenticated = true;
          _emailController.text = user.email ?? '';
          _nameController.text = user.displayName ?? '';
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Google account verified. Complete profile registration.')),
          );
        }
      }
    } else {
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
    if (phone.isEmpty || phone.length < 10) {
      setState(() {
        _errorMessage = 'Please enter a valid 10-digit mobile number.';
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
        _errorMessage = 'Please enter the 6-digit verification code.';
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
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Account already exists! Redirecting to login...')),
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

    final result = await _authService.signup(name, email, phone: phone);

    setState(() {
      _isLoading = false;
    });

    if (result['success'] == true) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Account registered successfully! Welcome to Arasamaippu AI.')),
        );
        Navigator.of(context).pushReplacementNamed('/main');
      }
    } else {
      setState(() {
        _errorMessage = result['message'] as String?;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC), // Modern off-white theme
      appBar: AppBar(
        title: const Text('Register Profile', style: TextStyle(fontWeight: FontWeight.bold)),
        centerTitle: true,
        elevation: 0,
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.black87,
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // App Logo Header
                  Center(
                    child: Column(
                      children: [
                        ScaleTransition(
                          scale: _scaleAnimation,
                          child: Container(
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              boxShadow: [
                                BoxShadow(
                                  color: theme.primaryColor.withAlpha(38),
                                  blurRadius: 20,
                                  spreadRadius: 4,
                                )
                              ],
                            ),
                            child: const AppLogo(size: 76),
                          ),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          _authenticated ? 'Complete Your Profile' : 'Create Your Account',
                          style: const TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF0F172A),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          _authenticated
                              ? 'Set your display name to complete database setup.'
                              : 'Select your preferred verification method to get started.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 13,
                            color: Colors.grey.shade600,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),

                  // Error Container
                  if (_errorMessage != null) ...[
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 300),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.red.shade50,
                        border: Border.all(color: Colors.red.shade200),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.error_outline, color: Colors.red.shade700, size: 20),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: TextStyle(color: Colors.red.shade800, fontSize: 13),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],

                  if (!_authenticated) ...[
                    // Step 1: Verification Card with Tab Switcher
                    Card(
                      elevation: 2,
                      shadowColor: Colors.black.withAlpha(15),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      child: Padding(
                        padding: const EdgeInsets.all(20.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            // Segmented Method Selector Tabs
                            Container(
                              decoration: BoxDecoration(
                                color: Colors.grey.shade100,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: TabBar(
                                controller: _tabController,
                                indicator: BoxDecoration(
                                  borderRadius: BorderRadius.circular(10),
                                  color: Colors.white,
                                  boxShadow: [
                                    BoxShadow(
                                      color: Colors.black.withAlpha(20),
                                      blurRadius: 4,
                                      offset: const Offset(0, 2),
                                    )
                                  ],
                                ),
                                labelColor: theme.primaryColor,
                                unselectedLabelColor: Colors.grey.shade600,
                                labelStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                                indicatorSize: TabBarIndicatorSize.tab,
                                dividerColor: Colors.transparent,
                                tabs: const [
                                  Tab(
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        GoogleLogo(size: 16),
                                        SizedBox(width: 6),
                                        Text('Google'),
                                      ],
                                    ),
                                  ),
                                  Tab(
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        Icon(Icons.phone_android, size: 16),
                                        SizedBox(width: 6),
                                        Text('Phone SMS'),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 20),

                            // Tab View Container
                            SizedBox(
                              height: _phoneCodeSent ? 160 : 130,
                              child: TabBarView(
                                controller: _tabController,
                                physics: const NeverScrollableScrollPhysics(),
                                children: [
                                  // Tab 1: Google Account Verification
                                  Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment: CrossAxisAlignment.stretch,
                                    children: [
                                      const Text(
                                        'Verify identity quickly using Google Account.',
                                        textAlign: TextAlign.center,
                                        style: TextStyle(fontSize: 12, color: Colors.grey),
                                      ),
                                      const SizedBox(height: 16),
                                      _isLoading
                                          ? const Center(child: CircularProgressIndicator())
                                          : ElevatedButton.icon(
                                              onPressed: _verifyWithGoogle,
                                              icon: const GoogleLogo(size: 18),
                                              label: const Text('Verify Google Account', style: TextStyle(fontWeight: FontWeight.bold)),
                                              style: ElevatedButton.styleFrom(
                                                backgroundColor: Colors.white,
                                                foregroundColor: Colors.black87,
                                                padding: const EdgeInsets.symmetric(vertical: 14),
                                                elevation: 1,
                                                side: BorderSide(color: Colors.grey.shade300),
                                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                              ),
                                            ),
                                    ],
                                  ),

                                  // Tab 2: Phone SMS Verification
                                  Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment: CrossAxisAlignment.stretch,
                                    children: [
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
                                        const SizedBox(height: 12),
                                        _isLoading
                                            ? const Center(child: CircularProgressIndicator())
                                            : ElevatedButton(
                                                onPressed: _verifySendPhoneCode,
                                                style: ElevatedButton.styleFrom(
                                                  backgroundColor: theme.primaryColor,
                                                  foregroundColor: Colors.white,
                                                  padding: const EdgeInsets.symmetric(vertical: 14),
                                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                                ),
                                                child: const Text('Send Verification Code', style: TextStyle(fontWeight: FontWeight.bold)),
                                              ),
                                      ] else ...[
                                        // Editable Phone Number Banner Above OTP Field
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                          decoration: BoxDecoration(
                                            color: theme.primaryColor.withAlpha(20),
                                            borderRadius: BorderRadius.circular(10),
                                            border: Border.all(color: theme.primaryColor.withAlpha(51)),
                                          ),
                                          child: Row(
                                            children: [
                                              Icon(Icons.phone_android, size: 18, color: theme.primaryColor),
                                              const SizedBox(width: 8),
                                              Expanded(
                                                child: Text(
                                                  'OTP sent to +91 ${_phoneController.text.trim()}',
                                                  style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                                                ),
                                              ),
                                              InkWell(
                                                onTap: () {
                                                  setState(() {
                                                    _phoneCodeSent = false;
                                                    _smsCodeController.clear();
                                                  });
                                                },
                                                borderRadius: BorderRadius.circular(6),
                                                child: Padding(
                                                  padding: const EdgeInsets.all(4.0),
                                                  child: Row(
                                                    mainAxisSize: MainAxisSize.min,
                                                    children: [
                                                      Icon(Icons.edit_outlined, size: 16, color: theme.primaryColor),
                                                      const SizedBox(width: 4),
                                                      Text(
                                                        'Edit',
                                                        style: TextStyle(
                                                          color: theme.primaryColor,
                                                          fontWeight: FontWeight.bold,
                                                          fontSize: 13,
                                                        ),
                                                      ),
                                                    ],
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        const SizedBox(height: 12),
                                        TextFormField(
                                          controller: _smsCodeController,
                                          keyboardType: TextInputType.number,
                                          maxLength: 6,
                                          decoration: InputDecoration(
                                            labelText: '6-digit SMS Code',
                                            hintText: 'Enter 6-digit code',
                                            counterText: '',
                                            prefixIcon: const Icon(Icons.lock_clock_outlined),
                                            border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                                          ),
                                        ),
                                        const SizedBox(height: 12),
                                        _isLoading
                                            ? const Center(child: CircularProgressIndicator())
                                            : ElevatedButton(
                                                onPressed: _verifyPhoneCode,
                                                style: ElevatedButton.styleFrom(
                                                  backgroundColor: theme.primaryColor,
                                                  foregroundColor: Colors.white,
                                                  padding: const EdgeInsets.symmetric(vertical: 14),
                                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                                ),
                                                child: const Text('Confirm Code', style: TextStyle(fontWeight: FontWeight.bold)),
                                              ),
                                      ],
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ] else ...[
                    // Step 2: User profile fields (Visible only when authenticated)
                    Card(
                      elevation: 2,
                      shadowColor: Colors.black.withAlpha(15),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      child: Padding(
                        padding: const EdgeInsets.all(20.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(4),
                                  decoration: const BoxDecoration(
                                    color: Colors.green,
                                    shape: BoxShape.circle,
                                  ),
                                  child: const Icon(Icons.check, color: Colors.white, size: 14),
                                ),
                                const SizedBox(width: 8),
                                const Expanded(
                                  child: Text(
                                    'Verified! Set Display Name',
                                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
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
                                  return 'Please enter your full name.';
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 16),

                            // Locked Email field
                            if (_emailController.text.isNotEmpty) ...[
                              TextFormField(
                                controller: _emailController,
                                readOnly: true,
                                decoration: InputDecoration(
                                  labelText: 'Email Address',
                                  prefixIcon: const Icon(Icons.email_outlined),
                                  suffixIcon: const Icon(Icons.lock, size: 16, color: Colors.grey),
                                  filled: true,
                                  fillColor: Colors.grey.shade100,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(10.0),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 16),
                            ],

                            // Locked Phone field
                            if (_phoneController.text.isNotEmpty) ...[
                              TextFormField(
                                controller: _phoneController,
                                readOnly: true,
                                decoration: InputDecoration(
                                  labelText: 'Phone Number',
                                  prefixIcon: const Icon(Icons.phone_outlined),
                                  suffixIcon: const Icon(Icons.lock, size: 16, color: Colors.grey),
                                  filled: true,
                                  fillColor: Colors.grey.shade100,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(10.0),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 20),
                            ],

                            // Complete Registration CTA
                            _isLoading
                                ? const Center(child: CircularProgressIndicator())
                                : ElevatedButton(
                                    onPressed: _handleSignup,
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: theme.primaryColor,
                                      foregroundColor: Colors.white,
                                      padding: const EdgeInsets.symmetric(vertical: 14),
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                    ),
                                    child: const Text(
                                      'Register Account',
                                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                                    ),
                                  ),
                          ],
                        ),
                      ),
                    ),
                  ],

                  const SizedBox(height: 20),
                  // Link back to Sign In
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Text("Already registered? ", style: TextStyle(color: Colors.black54)),
                      GestureDetector(
                        onTap: () {
                          Navigator.of(context).pop();
                        },
                        child: Text(
                          "Sign In",
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
      ),
    );
  }
}
