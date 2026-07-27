import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/history_service.dart';
import '../widgets/app_logo.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  final HistoryService _historyService = HistoryService();
  List<Map<String, dynamic>> _historyItems = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    if (!mounted) return;
    setState(() {
      _isLoading = true;
    });
    final items = await _historyService.getHistory();
    if (mounted) {
      setState(() {
        _historyItems = items;
        _isLoading = false;
      });
    }
  }

  String _formatTimestamp(String isoString) {
    try {
      final dateTime = DateTime.parse(isoString);
      // Format as e.g. "Jul 25, 22:15"
      final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      final month = months[dateTime.month - 1];
      final day = dateTime.day;
      final hour = dateTime.hour.toString().padLeft(2, '0');
      final minute = dateTime.minute.toString().padLeft(2, '0');
      return '$month $day, $hour:$minute';
    } catch (_) {
      return '';
    }
  }

  void _showHistoryDetails(BuildContext context, Map<String, dynamic> item) {
    final rawArticles = item['retrieved_articles'] as List<dynamic>? ?? [];
    final List<Map<String, String>> retrievedArticles = rawArticles.map((item) {
      final map = item as Map<String, dynamic>;
      return {
        'number': map['number'] as String? ?? '',
        'title': map['title'] as String? ?? '',
        'part': map['part'] as String? ?? '',
        'content': map['content'] as String? ?? '',
      };
    }).toList();

    final citations = List<String>.from(item['citations'] ?? []);

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16.0),
          ),
          title: Text(
            item['query'] as String? ?? 'Search Details',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
          content: SizedBox(
            width: double.maxFinite,
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Citations chips list
                  if (citations.isNotEmpty) ...[
                    const Text(
                      'Citations (Tap to verify):',
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.black54),
                    ),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 4.0,
                      children: citations.map((citation) {
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
                          onPressed: () => _showArticleDialog(context, citation, retrievedArticles),
                        );
                      }).toList(),
                    ),
                    const Divider(height: 20),
                  ],
                  
                  // Response body text formatted
                  const Text(
                    'Response:',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.black54),
                  ),
                  const SizedBox(height: 6),
                  MarkdownBody(
                    data: item['answer'] as String? ?? '',
                    styleSheet: MarkdownStyleSheet(
                      p: const TextStyle(fontSize: 14.0, height: 1.4, color: Colors.black87),
                      h3: const TextStyle(fontSize: 15.0, fontWeight: FontWeight.bold, color: Color(0xFF1E3A8A)),
                      h4: const TextStyle(fontSize: 14.0, fontWeight: FontWeight.bold, color: Color(0xFF1E3A8A)),
                      em: const TextStyle(fontSize: 13.0, fontStyle: FontStyle.italic, color: Colors.black54),
                      strong: const TextStyle(fontWeight: FontWeight.bold, color: Colors.black87),
                    ),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close'),
            ),
          ],
        );
      },
    );
  }

  void _showArticleDialog(BuildContext context, String citation, List<Map<String, String>> articles) {
    final match = RegExp(r'\d+[A-Z]?').firstMatch(citation);
    final number = match != null ? match.group(0) : '';
    
    final article = articles.firstWhere(
      (element) => element['number'] == number,
      orElse: () => <String, String>{},
    );
    
    if (article.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Original text for $citation is not cached in this item.'),
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
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
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
                    style: const TextStyle(fontSize: 14.0, height: 1.4, color: Colors.black87),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close'),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            AppLogo(size: 24, showShadow: false),
            SizedBox(width: 8),
            Text('Search History'),
          ],
        ),
        elevation: 1,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadHistory,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _historyItems.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.history,
                        size: 64,
                        color: Colors.grey.shade300,
                      ),
                      const SizedBox(height: 16),
                      const Text(
                        'No search history yet.',
                        style: TextStyle(fontSize: 16, color: Colors.grey),
                      ),
                    ],
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(8.0),
                  itemCount: _historyItems.length,
                  itemBuilder: (context, index) {
                    final item = _historyItems[index];
                    final citations = List<String>.from(item['citations'] ?? []);
                    
                    return Card(
                      elevation: 1,
                      margin: const EdgeInsets.symmetric(vertical: 4.0, horizontal: 8.0),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      child: ListTile(
                        contentPadding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                        title: Text(
                          item['query'] as String? ?? '',
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14.0),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        subtitle: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const SizedBox(height: 4),
                            if (citations.isNotEmpty) ...[
                              Text(
                                'Cited: ${citations.join(', ')}',
                                style: const TextStyle(fontSize: 11, color: Colors.black54),
                              ),
                              const SizedBox(height: 2),
                            ],
                            Text(
                              _formatTimestamp(item['timestamp'] as String? ?? ''),
                              style: const TextStyle(fontSize: 10, color: Colors.grey),
                            ),
                          ],
                        ),
                        trailing: const Icon(Icons.arrow_forward_ios, size: 14),
                        onTap: () => _showHistoryDetails(context, item),
                      ),
                    );
                  },
                ),
    );
  }
}
