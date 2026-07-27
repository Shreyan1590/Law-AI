import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/services/api_service.dart';

void main() {
  test('ApiService bundles the production backend URL by default', () {
    expect(ApiService.baseUrl, 'https://arasamaippu-ai-backend.onrender.com');
  });
}
