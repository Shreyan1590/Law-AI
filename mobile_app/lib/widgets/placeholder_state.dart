import 'package:flutter/material.dart';

/// A polished, reusable placeholder state widget for Empty, Error, Offline,
/// No Search Results, Permission Denied, and Session Expired states.
///
/// Design tokens follow the UI/UX spec:
///   Success → #10B981 / #ECFDF5
///   Error   → #EF4444 / #FEF2F2
///   Warning → #F59E0B / #FFFBEB
///   Neutral → #4F46E5 / #EEF2FF  or  #64748B / #F8FAFC
class PlaceholderState extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final Color backgroundColor;
  final String title;
  final String description;
  final String? actionLabel;
  final VoidCallback? onAction;
  final IconData? actionIcon;

  const PlaceholderState({
    super.key,
    required this.icon,
    required this.iconColor,
    required this.backgroundColor,
    required this.title,
    required this.description,
    this.actionLabel,
    this.onAction,
    this.actionIcon,
  });

  // ─── Factory constructors for each design-spec state ───

  /// Empty State: Soft indigo icon, "Nothing here yet"
  factory PlaceholderState.empty({
    String title = 'Nothing here yet',
    String description = 'Start exploring and create your first entry to see it listed here.',
    String? actionLabel = 'Start Exploring',
    VoidCallback? onAction,
  }) {
    return PlaceholderState(
      icon: Icons.space_dashboard_outlined,
      iconColor: const Color(0xFF4F46E5),
      backgroundColor: const Color(0xFFEEF2FF),
      title: title,
      description: description,
      actionLabel: actionLabel,
      onAction: onAction,
      actionIcon: Icons.add,
    );
  }

  /// Error State: Red alert icon, "Something went wrong"
  factory PlaceholderState.error({
    String title = 'Something went wrong',
    String description = 'We encountered an unexpected issue. Don\'t worry, your data is safe.',
    String? actionLabel = 'Try Again',
    VoidCallback? onAction,
  }) {
    return PlaceholderState(
      icon: Icons.error_outline_rounded,
      iconColor: const Color(0xFFEF4444),
      backgroundColor: const Color(0xFFFEF2F2),
      title: title,
      description: description,
      actionLabel: actionLabel,
      onAction: onAction,
      actionIcon: Icons.refresh_rounded,
    );
  }

  /// No Internet State: Wi-Fi off icon, "You're offline"
  factory PlaceholderState.offline({
    String title = 'You\'re offline',
    String description = 'Please check your Wi-Fi or cellular network connection and try again.',
    String? actionLabel = 'Check Connection',
    VoidCallback? onAction,
  }) {
    return PlaceholderState(
      icon: Icons.wifi_off_rounded,
      iconColor: const Color(0xFF64748B),
      backgroundColor: const Color(0xFFF1F5F9),
      title: title,
      description: description,
      actionLabel: actionLabel,
      onAction: onAction,
    );
  }

  /// Slow Network State: Hourglass, "Network is slow"
  factory PlaceholderState.slowNetwork({
    String title = 'Network is slow',
    String description = 'Hang tight! Connection is taking a little longer than usual.',
    String? actionLabel,
    VoidCallback? onAction,
  }) {
    return PlaceholderState(
      icon: Icons.hourglass_top_rounded,
      iconColor: const Color(0xFFF59E0B),
      backgroundColor: const Color(0xFFFFFBEB),
      title: title,
      description: description,
      actionLabel: actionLabel,
      onAction: onAction,
    );
  }

  /// No Search Results: Magnifying glass, "No results found"
  factory PlaceholderState.noResults({
    String title = 'No results found',
    String description = 'We couldn\'t find anything matching your keywords. Try different search terms.',
    String? actionLabel = 'Clear Filters',
    VoidCallback? onAction,
  }) {
    return PlaceholderState(
      icon: Icons.search_off_rounded,
      iconColor: const Color(0xFF64748B),
      backgroundColor: const Color(0xFFF8FAFC),
      title: title,
      description: description,
      actionLabel: actionLabel,
      onAction: onAction,
    );
  }

  /// Permission Denied: Lock icon, "Permission required"
  factory PlaceholderState.permissionDenied({
    String title = 'Permission required',
    String description = 'Please allow access in your device settings to unlock and use this feature.',
    String? actionLabel = 'Open Settings',
    VoidCallback? onAction,
  }) {
    return PlaceholderState(
      icon: Icons.lock_person_outlined,
      iconColor: const Color(0xFF4F46E5),
      backgroundColor: const Color(0xFFEEF2FF),
      title: title,
      description: description,
      actionLabel: actionLabel,
      onAction: onAction,
    );
  }

  /// Session Expired: Clock icon, "Session expired"
  factory PlaceholderState.sessionExpired({
    String title = 'Session expired',
    String description = 'Your session has expired for security reasons. Please log in again to continue.',
    String? actionLabel = 'Log In Again',
    VoidCallback? onAction,
  }) {
    return PlaceholderState(
      icon: Icons.access_time_rounded,
      iconColor: const Color(0xFFF59E0B),
      backgroundColor: const Color(0xFFFFFBEB),
      title: title,
      description: description,
      actionLabel: actionLabel,
      onAction: onAction,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32.0, vertical: 24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            // Circular icon container
            TweenAnimationBuilder<double>(
              tween: Tween(begin: 0.0, end: 1.0),
              duration: const Duration(milliseconds: 500),
              curve: Curves.elasticOut,
              builder: (context, value, child) {
                return Transform.scale(scale: value, child: child);
              },
              child: Container(
                padding: const EdgeInsets.all(22),
                decoration: BoxDecoration(
                  color: backgroundColor,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: iconColor.withValues(alpha: 0.12),
                      blurRadius: 20,
                      offset: const Offset(0, 6),
                    ),
                  ],
                ),
                child: Icon(icon, size: 48, color: iconColor),
              ),
            ),

            const SizedBox(height: 24),

            // Title text
            Text(
              title,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: Color(0xFF0F172A), // Slate-900
                letterSpacing: -0.3,
              ),
              textAlign: TextAlign.center,
            ),

            const SizedBox(height: 10),

            // Description body
            Text(
              description,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w400,
                color: Color(0xFF64748B), // Slate-500
                height: 1.5,
              ),
              textAlign: TextAlign.center,
            ),

            // Optional CTA button
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: 28),
              ElevatedButton.icon(
                onPressed: onAction,
                icon: actionIcon != null
                    ? Icon(actionIcon, size: 18)
                    : const SizedBox.shrink(),
                label: Text(
                  actionLabel!,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: iconColor,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 14,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  elevation: 2,
                  shadowColor: iconColor.withValues(alpha: 0.3),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
