class ChatMessage {
  final String text;
  final bool isUser;
  final List<String> citations;
  final DateTime timestamp;
  final List<Map<String, String>> retrievedArticles; // List of {number, title, part, content} maps

  ChatMessage({
    required this.text,
    required this.isUser,
    this.citations = const [],
    required this.timestamp,
    this.retrievedArticles = const [],
  });
}
