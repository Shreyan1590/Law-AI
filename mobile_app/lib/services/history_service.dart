import 'package:shared_preferences/shared_preferences.dart';
import 'package:cloud_firestore/cloud_firestore.dart';

class HistoryService {
  static const String _keyUserEmail = 'auth_user_email';

  /// Saves a search transaction directly to the Firestore database.
  Future<void> saveToHistory({
    required String query,
    required String answer,
    required List<String> citations,
    required List<Map<String, String>> retrievedArticles,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final email = prefs.getString(_keyUserEmail) ?? '';

      if (email.isNotEmpty) {
        await FirebaseFirestore.instance.collection('history').add({
          'userEmail': email.trim().toLowerCase(),
          'query': query,
          'answer': answer,
          'citations': citations,
          'retrievedArticles': retrievedArticles,
          'timestamp': FieldValue.serverTimestamp(),
        });
      }
    } catch (_) {}
  }

  /// Retrieves the search history list from the Cloud Firestore database.
  /// Uses client-side sorting to bypass requirement of composite indices.
  Future<List<Map<String, dynamic>>> getHistory() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final email = prefs.getString(_keyUserEmail) ?? '';

      if (email.isEmpty) {
        return <Map<String, dynamic>>[];
      }

      final querySnapshot = await FirebaseFirestore.instance
          .collection('history')
          .where('userEmail', isEqualTo: email.trim().toLowerCase())
          .get();

      final List<Map<String, dynamic>> items = querySnapshot.docs.map((doc) {
        final data = doc.data();
        
        final List<dynamic> rawArticles = data['retrievedArticles'] as List<dynamic>? ?? [];
        final List<Map<String, String>> retrieved = rawArticles.map((item) {
          final map = item as Map<String, dynamic>;
          return {
            'number': map['number'] as String? ?? '',
            'title': map['title'] as String? ?? '',
            'part': map['part'] as String? ?? '',
            'content': map['content'] as String? ?? '',
          };
        }).toList();

        return {
          'id': doc.id,
          'query': data['query'] as String? ?? '',
          'answer': data['answer'] as String? ?? '',
          'citations': List<String>.from(data['citations'] ?? []),
          'retrieved_articles': retrieved,
          'timestamp': data['timestamp'] is Timestamp 
              ? (data['timestamp'] as Timestamp).toDate().toIso8601String() 
              : DateTime.now().toIso8601String(),
        };
      }).toList();

      // Sort client-side descending (latest first)
      items.sort((a, b) => b['timestamp'].compareTo(a['timestamp']));
      return items;
    } catch (_) {
      return <Map<String, dynamic>>[];
    }
  }

  /// Clears search history from Cloud Firestore.
  Future<void> clearHistory() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final email = prefs.getString(_keyUserEmail) ?? '';

      if (email.isNotEmpty) {
        final querySnapshot = await FirebaseFirestore.instance
            .collection('history')
            .where('userEmail', isEqualTo: email.trim().toLowerCase())
            .get();

        for (var doc in querySnapshot.docs) {
          await doc.reference.delete();
        }
      }
    } catch (_) {}
  }
}
