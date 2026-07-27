import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter/foundation.dart';

class ApiService {
  // Replace this with your Render deployment URL once deployed (e.g., https://your-app.onrender.com).
  static String get baseUrl {
    if (kIsWeb) {
      return 'http://localhost:8000'; // Local PC address for Chrome Web
    }
    return 'http://10.0.2.2:8000'; // Special redirect to local PC for Android Emulator
  }

  /// Sends a question to the backend FastAPI server `/ask` endpoint.
  Future<Map<String, dynamic>> askQuestion(String question, {String? email}) async {
    final url = Uri.parse('$baseUrl/ask');
    
    try {
      final response = await http.post(
        url,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: jsonEncode({
          'question': question,
          if (email != null && email.isNotEmpty) 'email': email,
        }),
      ).timeout(
        const Duration(seconds: 45), // Generous timeout to allow Render free tier to wake up (cold start)
      );

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        final rawArticles = decoded['retrieved_articles'] as List<dynamic>? ?? [];
        final parsedArticles = rawArticles.map((item) {
          final map = item as Map<String, dynamic>;
          return {
            'number': map['number'] as String? ?? '',
            'title': map['title'] as String? ?? '',
            'part': map['part'] as String? ?? '',
            'content': map['content'] as String? ?? '',
          };
        }).toList();

        return {
          'success': true,
          'answer': decoded['answer'] as String,
          'citations': List<String>.from(decoded['articles_cited'] ?? []),
          'retrieved_articles': parsedArticles,
        };
      } else {
        // Handle server errors (e.g., 500, 503 database not ready)
        String errorMessage = 'Server returned an error (${response.statusCode}).';
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          if (decoded.containsKey('detail')) {
            errorMessage = decoded['detail'] as String;
          }
        } catch (_) {}
        
        return {
          'success': false,
          'answer': 'Error: $errorMessage Please try again.',
          'citations': <String>[],
          'retrieved_articles': <Map<String, String>>[],
        };
      }
    } on http.ClientException catch (e) {
      return {
        'success': false,
        'answer': 'Could not connect to the backend server. Please verify the server is running. (${e.message})',
        'citations': <String>[],
        'retrieved_articles': <Map<String, String>>[],
      };
    } catch (e) {
      return {
        'success': false,
        'answer': 'Error connecting to server. If the server is sleeping, it may take a minute to boot up. ($e)',
        'citations': <String>[],
        'retrieved_articles': <Map<String, String>>[],
      };
    }
  }
}
