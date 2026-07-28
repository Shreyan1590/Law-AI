import 'package:flutter/material.dart';

/// The 10 distinct states supported by the Animated Placeholder Overlay system.
enum OverlayStateConfig {
  empty,
  loading,
  error,
  noInternet,
  slowNetwork,
  noSearchResults,
  permissionDenied,
  sessionExpired,
  formValidation,
  success,
}

/// A backward-compatible wrapper to preserve current calls in the app (e.g. signup, profile).
class SuccessOverlay {
  /// Shows the success overlay with full scale and fade animations.
  static Future<void> show(
    BuildContext context, {
    String title = 'Action completed successfully!',
    String description = 'Your details have been saved and updated. You\'re ready to go.',
    String? actionLabel = 'Continue',
    VoidCallback? onAction,
    Duration? autoDismissDuration,
  }) {
    return AnimatedPlaceholderOverlay.show(
      context,
      state: OverlayStateConfig.success,
      customTitle: title,
      customDescription: description,
      actionLabel: actionLabel,
      onAction: onAction,
      autoDismissDuration: autoDismissDuration,
    );
  }
}

/// A unified overlay widget that displays one of the 10 animated placeholder states.
/// Centered, dims the background, blocks interaction, and triggers smooth fade/scale animations.
class AnimatedPlaceholderOverlay extends StatefulWidget {
  final OverlayStateConfig state;
  final String? customTitle;
  final String? customDescription;
  final String? actionLabel;
  final VoidCallback? onAction;
  final Duration? autoDismissDuration;

  const AnimatedPlaceholderOverlay({
    super.key,
    required this.state,
    this.customTitle,
    this.customDescription,
    this.actionLabel,
    this.onAction,
    this.autoDismissDuration,
  });

  /// Shows the AnimatedPlaceholderOverlay as a modal dialog with custom entry/exit transitions.
  static Future<void> show(
    BuildContext context, {
    required OverlayStateConfig state,
    String? customTitle,
    String? customDescription,
    String? actionLabel,
    VoidCallback? onAction,
    Duration? autoDismissDuration,
  }) {
    return showDialog(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.black.withValues(alpha: 0.4), // 40% dimmed background
      builder: (ctx) => AnimatedPlaceholderOverlay(
        state: state,
        customTitle: customTitle,
        customDescription: customDescription,
        actionLabel: actionLabel,
        onAction: onAction,
        autoDismissDuration: autoDismissDuration,
      ),
    );
  }

  @override
  State<AnimatedPlaceholderOverlay> createState() => _AnimatedPlaceholderOverlayState();
}

class _AnimatedPlaceholderOverlayState extends State<AnimatedPlaceholderOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _scaleAnim;
  late final Animation<double> _fadeAnim;
  bool _isDismissing = false;

  @override
  void initState() {
    super.initState();
    // 300ms transition time as specified
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );

    _scaleAnim = Tween<double>(begin: 0.8, end: 1.0).animate(
      CurvedAnimation(
        parent: _controller,
        curve: Curves.easeOut, // ease-out for entry
        reverseCurve: Curves.easeIn, // ease-in for exit
      ),
    );

    _fadeAnim = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _controller,
        curve: Curves.easeOut,
        reverseCurve: Curves.easeIn,
      ),
    );

    _controller.forward();

    // Handle auto-dismiss if specified
    if (widget.autoDismissDuration != null) {
      Future.delayed(widget.autoDismissDuration!, () {
        if (mounted && !_isDismissing) {
          _dismiss();
        }
      });
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _dismiss() {
    if (_isDismissing) return;
    setState(() {
      _isDismissing = true;
    });
    // Exit transition: Fade-out + scale-down (ease-in)
    _controller.reverse().then((_) {
      if (mounted) {
        Navigator.of(context).pop();
        widget.onAction?.call();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    // ─── Setup UI Configuration based on the Active State ───
    final IconData iconData;
    final Color iconColor;
    final Color backgroundColor;
    final String defaultTitle;
    final String defaultDescription;
    final String? defaultActionLabel;
    final bool showSpinner;

    switch (widget.state) {
      case OverlayStateConfig.empty:
        iconData = Icons.folder_open_rounded;
        iconColor = const Color(0xFF607D8B); // Neutral Gray/Blue
        backgroundColor = const Color(0xFFECEFF1);
        defaultTitle = 'Nothing here yet. Start exploring!';
        defaultDescription = 'There is no history or documents saved yet. Begin your legal research now.';
        defaultActionLabel = 'Explore Now';
        showSpinner = false;
        break;

      case OverlayStateConfig.loading:
        iconData = Icons.hourglass_bottom_rounded; // Fallback
        iconColor = const Color(0xFF2196F3); // Neutral Blue
        backgroundColor = const Color(0xFFE3F2FD);
        defaultTitle = 'Loading your content… please wait.';
        defaultDescription = 'Fetching legal resources and preparing the offline assistant.';
        defaultActionLabel = null;
        showSpinner = true; // Shows animated spinner instead of static icon
        break;

      case OverlayStateConfig.error:
        iconData = Icons.warning_amber_rounded; // Alert triangle
        iconColor = const Color(0xFFF44336); // Red
        backgroundColor = const Color(0xFFFFEBEE);
        defaultTitle = 'Something went wrong.';
        defaultDescription = 'An unexpected error occurred. Please try again later.';
        defaultActionLabel = 'Retry';
        showSpinner = false;
        break;

      case OverlayStateConfig.noInternet:
        iconData = Icons.wifi_off_rounded;
        iconColor = const Color(0xFF607D8B); // Gray
        backgroundColor = const Color(0xFFECEFF1);
        defaultTitle = 'You’re offline. Check your connection.';
        defaultDescription = 'Your internet connection was lost. Switch to local database search.';
        defaultActionLabel = null;
        showSpinner = false;
        break;

      case OverlayStateConfig.slowNetwork:
        iconData = Icons.hourglass_empty_rounded; // Hourglass/snail representation
        iconColor = const Color(0xFFFF9800); // Orange
        backgroundColor = const Color(0xFFFFF3E0);
        defaultTitle = 'Network is slow, hang tight.';
        defaultDescription = 'The connection to the cloud assistant is taking longer than usual.';
        defaultActionLabel = null;
        showSpinner = false;
        break;

      case OverlayStateConfig.noSearchResults:
        iconData = Icons.search_off_rounded;
        iconColor = const Color(0xFF2196F3); // Blue
        backgroundColor = const Color(0xFFE3F2FD);
        defaultTitle = 'No results found. Try different keywords.';
        defaultDescription = 'We couldn\'t find any matching legal clauses. Rephrase your search.';
        defaultActionLabel = 'Search Again';
        showSpinner = false;
        break;

      case OverlayStateConfig.permissionDenied:
        iconData = Icons.lock_outline_rounded;
        iconColor = const Color(0xFFF44336); // Red/Gray
        backgroundColor = const Color(0xFFFFEBEE);
        defaultTitle = 'Permission denied. Please allow access.';
        defaultDescription = 'Storage or device access permissions are required to view original PDFs.';
        defaultActionLabel = 'Open Settings';
        showSpinner = false;
        break;

      case OverlayStateConfig.sessionExpired:
        iconData = Icons.access_time_rounded; // Clock icon
        iconColor = const Color(0xFFFF9800); // Orange
        backgroundColor = const Color(0xFFFFF3E0);
        defaultTitle = 'Your session has expired. Log in again.';
        defaultDescription = 'For security reasons, your active session has closed. Please log in.';
        defaultActionLabel = 'Log In';
        showSpinner = false;
        break;

      case OverlayStateConfig.formValidation:
        iconData = Icons.error_outline_rounded; // Red border indicator
        iconColor = const Color(0xFFF44336); // Red
        backgroundColor = const Color(0xFFFFEBEE);
        defaultTitle = 'Please correct the errors before submitting.';
        defaultDescription = 'Some fields have incorrect values. Check highlighting.';
        defaultActionLabel = null;
        showSpinner = false;
        break;

      case OverlayStateConfig.success:
        iconData = Icons.check_circle_outline_rounded;
        iconColor = const Color(0xFF4CAF50); // Green
        backgroundColor = const Color(0xFFE8F5E9);
        defaultTitle = 'Action completed successfully!';
        defaultDescription = 'Your details have been saved and updated successfully.';
        defaultActionLabel = 'Continue';
        showSpinner = false;
        break;
    }

    final title = widget.customTitle ?? defaultTitle;
    final description = widget.customDescription ?? defaultDescription;
    final actionBtnLabel = widget.actionLabel ?? defaultActionLabel;

    return Dialog(
      backgroundColor: Colors.transparent,
      elevation: 0,
      child: FadeTransition(
        opacity: _fadeAnim,
        child: Center(
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 16),
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 30),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.12),
                  blurRadius: 24,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Top: Animated Visual (Spinner or Icon)
                ScaleTransition(
                  scale: _scaleAnim,
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: backgroundColor,
                      shape: BoxShape.circle,
                    ),
                    child: showSpinner
                        ? SizedBox(
                            width: 48,
                            height: 48,
                            child: CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(iconColor),
                              strokeWidth: 4,
                            ),
                          )
                        : Icon(
                            iconData,
                            size: 48,
                            color: iconColor,
                          ),
                  ),
                ),

                const SizedBox(height: 20),

                // Middle: Consistent Typography (Sans-serif message)
                Text(
                  title,
                  style: const TextStyle(
                    fontFamily: 'Plus Jakarta Sans',
                    fontSize: 16, // Specified 16px message
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF1E293B), // Dark Navy
                    height: 1.35,
                  ),
                  textAlign: TextAlign.center,
                ),

                const SizedBox(height: 8),

                Text(
                  description,
                  style: const TextStyle(
                    fontFamily: 'Plus Jakarta Sans',
                    fontSize: 13,
                    fontWeight: FontWeight.w400,
                    color: Color(0xFF64748B),
                    height: 1.45,
                  ),
                  textAlign: TextAlign.center,
                ),

                // Bottom: Button Actions with Ripple effect
                if (actionBtnLabel != null) ...[
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _dismiss,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: iconColor,
                        foregroundColor: Colors.white,
                        elevation: 1,
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                        // Soft glow shadowing matching the spec
                        shadowColor: iconColor.withValues(alpha: 0.4),
                      ),
                      child: Text(
                        actionBtnLabel,
                        style: const TextStyle(
                          fontFamily: 'Plus Jakarta Sans',
                          fontSize: 14, // Specified 14px button text
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
