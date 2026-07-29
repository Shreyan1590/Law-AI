import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

class ProVeloceBranding extends StatelessWidget {
  final double logoHeight;
  final double fontSize;
  final FontWeight fontWeight;
  final Color textColor;
  final double spacing;
  final MainAxisAlignment alignment;
  final double? letterSpacing;

  const ProVeloceBranding({
    super.key,
    this.logoHeight = 12,
    this.fontSize = 11,
    this.fontWeight = FontWeight.w600,
    this.textColor = Colors.black45,
    this.spacing = 4,
    this.alignment = MainAxisAlignment.center,
    this.letterSpacing,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: alignment,
      mainAxisSize: MainAxisSize.min,
      children: [
        SvgPicture.asset(
          'assets/proveloce_logo.svg',
          height: logoHeight,
          fit: BoxFit.contain,
        ),
        SizedBox(width: spacing),
        Text(
          'A Product by ProVeloce',
          style: TextStyle(
            fontSize: fontSize,
            fontWeight: fontWeight,
            color: textColor,
            letterSpacing: letterSpacing,
          ),
        ),
      ],
    );
  }
}
