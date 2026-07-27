import 'package:flutter/material.dart';

class GoogleLogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final Paint paint = Paint()..style = PaintingStyle.fill;

    // Scale our paths to fit the given size (we assume original viewport is 24x24)
    final double scaleX = size.width / 24.0;
    final double scaleY = size.height / 24.0;
    canvas.scale(scaleX, scaleY);

    // Path 1 (Blue): M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z
    paint.color = const Color(0xFF4285F4);
    final Path path1 = Path()
      ..moveTo(22.56, 12.25)
      ..relativeCubicTo(0, -0.78, -0.07, -1.53, -0.2, -2.25)
      ..lineTo(12, 10)
      ..lineTo(12, 14.26)
      ..lineTo(17.92, 14.26)
      ..relativeCubicTo(-0.26, 1.37, -1.04, 2.53, -2.21, 3.31)
      ..relativeLineTo(0, 2.77)
      ..relativeLineTo(3.57, 0)
      ..relativeCubicTo(2.08, -1.92, 3.28, -4.74, 3.28, -8.09)
      ..close();
    canvas.drawPath(path1, paint);

    // Path 2 (Green): M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z
    paint.color = const Color(0xFF34A853);
    final Path path2 = Path()
      ..moveTo(12, 23)
      ..relativeCubicTo(2.97, 0, 5.46, -0.98, 7.28, -2.66)
      ..relativeLineTo(-3.57, -2.77)
      ..relativeCubicTo(-0.98, 0.66, -2.23, 1.06, -3.71, 1.06)
      ..relativeCubicTo(-2.86, 0, -5.29, -1.93, -6.16, -4.53)
      ..lineTo(2.18, 14.1)
      ..relativeLineTo(0, 2.84)
      ..relativeCubicTo(1.81, 3.59, 5.52, 6.06, 9.82, 6.06)
      ..close();
    canvas.drawPath(path2, paint);

    // Path 3 (Yellow): M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z
    paint.color = const Color(0xFFFBBC05);
    final Path path3 = Path()
      ..moveTo(5.84, 14.09)
      ..relativeCubicTo(-0.22, -0.66, -0.35, -1.36, -0.35, -2.09)
      ..relativeCubicTo(0, -0.73, 0.13, -1.43, 0.35, -2.09)
      ..lineTo(5.84, 7.06)
      ..lineTo(2.18, 7.06)
      ..relativeCubicTo(-0.75, 1.49, -1.18, 3.16, -1.18, 4.94)
      ..relativeCubicTo(0, 1.78, 0.43, 3.45, 1.18, 4.94)
      ..relativeLineTo(2.85, -2.22)
      ..relativeLineTo(0.81, -0.63)
      ..close();
    canvas.drawPath(path3, paint);

    // Path 4 (Red): M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z
    paint.color = const Color(0xFFEA4335);
    final Path path4 = Path()
      ..moveTo(12, 5.38)
      ..relativeCubicTo(1.62, 0, 3.06, 0.56, 4.21, 1.64)
      ..relativeLineTo(3.15, -3.15)
      ..relativeCubicTo(-2.91, -2.71, -5.39, -3.8, -8.36, -3.8)
      ..relativeCubicTo(-4.3, 0, -8.01, 2.47, -9.82, 6.06)
      ..relativeLineTo(3.66, 2.84)
      ..relativeCubicTo(0.87, -2.6, 3.3, -4.52, 6.16, -4.52)
      ..close();
    canvas.drawPath(path4, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class GoogleLogo extends StatelessWidget {
  final double size;
  const GoogleLogo({super.key, this.size = 24.0});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: GoogleLogoPainter(),
    );
  }
}
