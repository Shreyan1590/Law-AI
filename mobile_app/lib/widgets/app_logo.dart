import 'package:flutter/material.dart';

class AppLogo extends StatelessWidget {
  final double size;
  final bool showShadow;

  const AppLogo({
    super.key,
    this.size = 48.0,
    this.showShadow = true,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: showShadow
          ? BoxDecoration(
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF1A365D).withValues(alpha: 0.25),
                  blurRadius: size * 0.18,
                  offset: Offset(0, size * 0.08),
                ),
              ],
            )
          : null,
      child: ClipOval(
        child: Image.asset(
          'assets/arasamaippu_ai_logo.png',
          width: size,
          height: size,
          fit: BoxFit.cover,
          errorBuilder: (context, error, stackTrace) {
            return Container(
              color: const Color(0xFF1A365D),
              alignment: Alignment.center,
              child: Icon(
                Icons.gavel,
                size: size * 0.5,
                color: const Color(0xFFD69E2E),
              ),
            );
          },
        ),
      ),
    );
  }
}
