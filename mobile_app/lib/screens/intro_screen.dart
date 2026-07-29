import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../widgets/app_logo.dart';

class IntroScreen extends StatefulWidget {
  const IntroScreen({super.key});

  @override
  State<IntroScreen> createState() => _IntroScreenState();
}

class _IntroScreenState extends State<IntroScreen> {
  final PageController _pageController = PageController();
  final AuthService _authService = AuthService();
  int _currentPage = 0;

  final List<Map<String, dynamic>> _onboardingData = [
    {
      'title': 'Samaneedhi AI',
      'subtitle': 'A Product by ProVeloce\n\nA professional AI search tool for the Constitution and Indian Laws.',
      'icon': Icons.gavel,
      'description': 'Search constitutional and criminal laws in plain English and retrieve answers instantly.',
    },
    {
      'title': 'Grounded RAG Search',
      'subtitle': 'Zero-cost offline database query pipeline.',
      'icon': Icons.storage,
      'description': 'Retrieves actual legal data directly from the official PDF. Zero AI hallucinations, running entirely locally.',
    },
    {
      'title': 'Interactive Verification',
      'subtitle': 'Fact-check provision sources instantly.',
      'icon': Icons.verified,
      'description': 'Tap on any citation chip to load and review the raw, official text of the provision in a scrollable view.',
    },
  ];

  Future<void> _onFinishOnboarding() async {
    try {
      await _authService.setOnboardingComplete();
    } catch (e) {
      debugPrint('Error saving onboarding state: $e');
    }
    
    if (mounted) {
      Navigator.pushReplacementNamed(context, '/login');
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Top Skip Button
            Align(
              alignment: Alignment.topRight,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                child: TextButton(
                  onPressed: _onFinishOnboarding,
                  child: Text(
                    'Skip',
                    style: TextStyle(
                      color: theme.primaryColor,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
            ),
            
            // Onboarding Pages Builder
            Expanded(
              child: PageView.builder(
                controller: _pageController,
                onPageChanged: (index) {
                  setState(() {
                    _currentPage = index;
                  });
                },
                itemCount: _onboardingData.length,
                itemBuilder: (context, index) {
                  final data = _onboardingData[index];
                  return Padding(
                    padding: const EdgeInsets.all(32.0),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        // Large Icon or AppLogo in Circle
                        index == 0
                            ? const AppLogo(size: 140)
                            : CircleAvatar(
                                radius: 70,
                                backgroundColor: theme.primaryColor.withValues(alpha: 0.1),
                                child: Icon(
                                  data['icon'] as IconData,
                                  size: 64,
                                  color: theme.primaryColor,
                                ),
                              ),
                        const SizedBox(height: 40),
                        
                        // Title
                        Text(
                          data['title'] as String,
                          style: const TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.bold,
                            color: Colors.black87,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                        
                        // Subtitle
                        Text(
                          data['subtitle'] as String,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            color: Colors.black54,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 16),
                        
                        // Description
                        Text(
                          data['description'] as String,
                          style: const TextStyle(
                            fontSize: 14,
                            height: 1.4,
                            color: Colors.grey,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
            
            // Bottom navigation row
            Padding(
              padding: const EdgeInsets.all(32.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // Indicators
                  Row(
                    children: List.generate(
                      _onboardingData.length,
                      (index) => Container(
                        margin: const EdgeInsets.symmetric(horizontal: 4.0),
                        width: _currentPage == index ? 16.0 : 8.0,
                        height: 8.0,
                        decoration: BoxDecoration(
                          color: _currentPage == index ? theme.primaryColor : Colors.grey.shade300,
                          borderRadius: BorderRadius.circular(4.0),
                        ),
                      ),
                    ),
                  ),
                  
                  // Next / Finish Button
                  ElevatedButton(
                    onPressed: () {
                      if (_currentPage == _onboardingData.length - 1) {
                        _onFinishOnboarding();
                      } else {
                        _pageController.nextPage(
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeIn,
                        );
                      }
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: theme.primaryColor,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(20),
                      ),
                    ),
                    child: Text(
                      _currentPage == _onboardingData.length - 1 ? 'Get Started' : 'Next',
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
