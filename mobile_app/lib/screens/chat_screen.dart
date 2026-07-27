import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../models/chat_message.dart';
import '../services/api_service.dart';
import '../widgets/app_logo.dart';
import '../services/auth_service.dart';
import '../services/history_service.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<ChatMessage> _messages = [];
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final ApiService _apiService = ApiService();
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    // Add introductory message from the legal assistant
    _messages.add(
      ChatMessage(
        text: "### Welcome to Arasamaippu AI.\n\n"
            "How can I help you find constitutional provisions today?\n\n"
            "**Examples:**\n"
            "• 'What is Article 21?'\n"
            "• 'What are my fundamental rights?'\n"
            "• 'Is primary education a right?'",
        isUser: false,
        timestamp: DateTime.now(),
      ),
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          0.0, // Because ListView is reversed, 0.0 is the bottom (latest message)
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _handleSubmitted(String text) async {
    if (text.trim().isEmpty) return;
    
    _textController.clear();
    final userMessage = ChatMessage(
      text: text,
      isUser: true,
      timestamp: DateTime.now(),
    );

    setState(() {
      _messages.insert(0, userMessage);
      _isLoading = true;
    });
    _scrollToBottom();

    // Check if user is logged in and retrieve email
    final authService = AuthService();
    final isLoggedIn = await authService.isLoggedIn();
    String? email;
    if (isLoggedIn) {
      email = await authService.getUserEmail();
    }

    // Call API service with optional email parameter
    final response = await _apiService.askQuestion(text, email: email);

    setState(() {
      _isLoading = false;
      _messages.insert(
        0,
        ChatMessage(
          text: response['answer'] as String,
          isUser: false,
          citations: response['citations'] as List<String>,
          retrievedArticles: List<Map<String, String>>.from(response['retrieved_articles'] ?? []),
          timestamp: DateTime.now(),
        ),
      );
    });
    _scrollToBottom();

    // Save search query transaction to local history (for guest offline fallback)
    if (response['success'] == true) {
      final historyService = HistoryService();
      await historyService.saveToHistory(
        query: text,
        answer: response['answer'] as String,
        citations: response['citations'] as List<String>,
        retrievedArticles: List<Map<String, String>>.from(response['retrieved_articles'] ?? []),
      );
    }
  }

  /// Displays the raw, original text of the retrieved constitutional provision in a modal dialog.
  void _showArticleDialog(BuildContext context, String citation, List<Map<String, String>> articles) {
    // Extract digit number from citation string (e.g. "Article 14" -> "14")
    final match = RegExp(r'\d+[A-Z]?').firstMatch(citation);
    final number = match != null ? match.group(0) : '';
    
    // Find the matching cached article detail
    final article = articles.firstWhere(
      (element) => element['number'] == number,
      orElse: () => <String, String>{},
    );
    
    if (article.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Original text for $citation is not cached in this response.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16.0),
          ),
          title: Row(
            children: [
              const Icon(Icons.gavel, color: Colors.amber),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Article ${article['number']}: ${article['title']}',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          content: SizedBox(
            width: double.maxFinite,
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (article['part']!.isNotEmpty) ...[
                    Text(
                      article['part']!,
                      style: const TextStyle(
                        fontSize: 13,
                        fontStyle: FontStyle.italic,
                        color: Colors.black54,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const Divider(height: 16),
                  ],
                  Text(
                    article['content']!,
                    style: const TextStyle(fontSize: 15, height: 1.45, color: Colors.black87),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text(
                'Close',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            AppLogo(size: 28, showShadow: false),
            SizedBox(width: 10),
            Text('Arasamaippu AI', style: TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
        elevation: 2,
      ),
      body: Column(
        children: [
          // Chat history area
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(12),
              reverse: true, // Anchor list to bottom
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final message = _messages[index];
                return _buildMessageBubble(message, theme);
              },
            ),
          ),
          
          // Loading Indicator
          if (_isLoading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.indigo),
                    ),
                  ),
                  SizedBox(width: 10),
                  Text(
                    'Searching constitutional text...',
                    style: TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
            ),
            
          // Input field and send button
          _buildInputArea(theme),
          
          // Persistent legal disclaimer footer
          _buildDisclaimerFooter(theme),
        ],
      ),
    );
  }

  Widget _buildMessageBubble(ChatMessage message, ThemeData theme) {
    final isUser = message.isUser;
    
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6.0),
      child: Row(
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[
            const AppLogo(size: 32, showShadow: false),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Column(
              crossAxisAlignment:
                  isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                // Render citation chips above response bubble if any exist (Clickable to redirect/inspect)
                if (!isUser && message.citations.isNotEmpty) ...[
                  Padding(
                    padding: const EdgeInsets.only(left: 4.0, bottom: 4.0),
                    child: Wrap(
                      spacing: 4.0,
                      children: message.citations.map((citation) {
                        return ActionChip(
                          labelPadding: const EdgeInsets.symmetric(horizontal: 4.0),
                          visualDensity: VisualDensity.compact,
                          backgroundColor: Colors.amber.shade100,
                          side: BorderSide(color: Colors.amber.shade300),
                          label: Text(
                            citation,
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                              color: Colors.amber.shade900,
                            ),
                          ),
                          onPressed: () => _showArticleDialog(context, citation, message.retrievedArticles),
                        );
                      }).toList(),
                    ),
                  ),
                ],
                
                // Actual message text bubble (renders Markdown for AI/Backend responses)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 10.0),
                  decoration: BoxDecoration(
                    color: isUser ? theme.primaryColor : Colors.grey.shade100,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(16),
                      topRight: const Radius.circular(16),
                      bottomLeft: Radius.circular(isUser ? 16 : 4),
                      bottomRight: Radius.circular(isUser ? 4 : 16),
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.03),
                        blurRadius: 4,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: isUser
                      ? Text(
                          message.text,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 15.0,
                            height: 1.35,
                          ),
                        )
                      : MarkdownBody(
                          data: message.text,
                          styleSheet: MarkdownStyleSheet(
                            p: const TextStyle(
                              color: Colors.black87,
                              fontSize: 15.0,
                              height: 1.45,
                            ),
                            h3: const TextStyle(
                              color: Color(0xFF1E3A8A), // Indigo for headers
                              fontSize: 16.0,
                              fontWeight: FontWeight.bold,
                              height: 1.5,
                            ),
                            h4: const TextStyle(
                              color: Color(0xFF1E3A8A), // Indigo for Article numbers
                              fontSize: 15.0,
                              fontWeight: FontWeight.bold,
                              height: 1.4,
                            ),
                            em: const TextStyle(
                              color: Colors.black54,
                              fontSize: 14.0,
                              fontStyle: FontStyle.italic,
                              fontWeight: FontWeight.w600,
                            ),
                            strong: const TextStyle(
                              color: Colors.black87,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                ),
              ],
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 8),
            CircleAvatar(
              backgroundColor: theme.colorScheme.secondary,
              radius: 16,
              child: const Icon(Icons.person, size: 16, color: Colors.white),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildInputArea(ThemeData theme) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border(
          top: BorderSide(color: Colors.grey.shade200),
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
      child: SafeArea(
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _textController,
                textCapitalization: TextCapitalization.sentences,
                onSubmitted: _isLoading ? null : _handleSubmitted,
                decoration: InputDecoration(
                  hintText: 'Ask about the Indian Constitution...',
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 10.0),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24.0),
                    borderSide: BorderSide(color: Colors.grey.shade300),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24.0),
                    borderSide: BorderSide(color: Colors.grey.shade200),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24.0),
                    borderSide: BorderSide(color: theme.primaryColor, width: 1.5),
                  ),
                  filled: true,
                  fillColor: Colors.grey.shade50,
                ),
                style: const TextStyle(fontSize: 15.0),
              ),
            ),
            const SizedBox(width: 8),
            IconButton(
              icon: const Icon(Icons.send),
              color: theme.primaryColor,
              onPressed: _isLoading
                  ? null
                  : () => _handleSubmitted(_textController.text),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDisclaimerFooter(ThemeData theme) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
      decoration: BoxDecoration(
        color: Colors.grey.shade50,
        border: Border(
          top: BorderSide(color: Colors.grey.shade200),
        ),
      ),
      child: const Text(
        'Disclaimer: This app provides informational summaries of the Constitution of India '
        'and does not constitute official legal advice. Always consult a qualified advocate.',
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: 10.0,
          color: Colors.grey,
          height: 1.25,
        ),
      ),
    );
  }
}
