import 'package:flutter/material.dart';

import '../../matching/matching_models.dart';
import '../../matching/matching_repository.dart';

class MatchesScreen extends StatefulWidget {
  const MatchesScreen({super.key, required this.repository});
  final MatchingRepository repository;

  @override
  State<MatchesScreen> createState() => _MatchesScreenState();
}

class _MatchesScreenState extends State<MatchesScreen> {
  List<MatchInboxItem>? _items;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final items = await widget.repository.listMatches();
      if (mounted) {
        setState(() {
          _items = items;
          _error = null;
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_items == null && _error == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(24),
              child: Text(_error!, textAlign: TextAlign.center),
            )
          else if (_items!.isEmpty)
            const _EmptyInbox()
          else
            for (final item in _items!)
              Card(
                child: ListTile(
                  leading: CircleAvatar(child: Text('${item.matchScore}')),
                  title: Text(item.title),
                  subtitle: Text(
                    '${item.company}\n${_formatDate(item.createdAt)}',
                  ),
                  isThreeLine: true,
                  trailing: item.isRead ? null : const Badge(),
                  onTap: () => _open(item),
                ),
              ),
        ],
      ),
    );
  }

  Future<void> _open(MatchInboxItem item) async {
    if (!item.isRead) {
      try {
        await widget.repository.markMatchRead(item.matchId);
        await _load();
      } catch (_) {
        // Reading the detail remains useful if the read receipt cannot be saved.
      }
    }
    if (!mounted) return;
    final rationale = item.matchData.entries
        .where(
          (entry) =>
              entry.value is String &&
              (entry.value as String).trim().isNotEmpty,
        )
        .take(4)
        .map((entry) => entry.value as String)
        .join('\n\n');
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                item.title,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              Text(item.company),
              const SizedBox(height: 16),
              Text(
                'Match score ${item.matchScore}/10',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 12),
              Text(
                rationale.isEmpty
                    ? 'Open the job listing for complete details.'
                    : rationale,
              ),
              if (item.sourceUrl != null) ...[
                const SizedBox(height: 16),
                SelectableText(item.sourceUrl!),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _formatDate(DateTime value) {
    final local = value.toLocal();
    return '${local.month}/${local.day}/${local.year}';
  }
}

class _EmptyInbox extends StatelessWidget {
  const _EmptyInbox();

  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.symmetric(vertical: 80, horizontal: 24),
    child: Column(
      children: [
        Icon(Icons.auto_awesome, size: 64),
        SizedBox(height: 16),
        Text(
          'No matches yet',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
        ),
        SizedBox(height: 8),
        Text(
          'Complete Automatic matching and your best new matches will appear here.',
          textAlign: TextAlign.center,
        ),
      ],
    ),
  );
}
