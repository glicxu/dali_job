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
                  leading: CircleAvatar(
                    child: Text(
                      item.overallScore != null
                          ? '${item.overallScore}'
                          : item.matchScore != null
                          ? '${item.matchScore}'
                          : '?',
                    ),
                  ),
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
    final saved = await showModalBottomSheet<bool>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) =>
          _MatchDetailSheet(item: item, repository: widget.repository),
    );
    if (saved == true) await _load();
  }

  String _formatDate(DateTime value) {
    final local = value.toLocal();
    return '${local.month}/${local.day}/${local.year}';
  }
}

class _MatchDetailSheet extends StatefulWidget {
  const _MatchDetailSheet({required this.item, required this.repository});

  final MatchInboxItem item;
  final MatchingRepository repository;

  @override
  State<_MatchDetailSheet> createState() => _MatchDetailSheetState();
}

class _MatchDetailSheetState extends State<_MatchDetailSheet> {
  late double _score;
  late final TextEditingController _rationale;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _score = (widget.item.userFeedback?.score ?? 50).toDouble();
    _rationale = TextEditingController(
      text: widget.item.userFeedback?.rationale ?? '',
    );
  }

  @override
  void dispose() {
    _rationale.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final v2 = item.v2Result;
    final rationale = item.matchData.entries
        .where(
          (entry) =>
              entry.value is String &&
              (entry.value as String).trim().isNotEmpty,
        )
        .take(4)
        .map((entry) => entry.value as String)
        .join('\n\n');
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          24,
          0,
          24,
          32 + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(item.title, style: Theme.of(context).textTheme.headlineSmall),
            Text(item.company),
            const SizedBox(height: 16),
            _ScoreSummary(item: item),
            if (v2 != null) ...[
              const SizedBox(height: 8),
              Text(v2.explanation.summary),
              _ExplanationSection(
                title: 'Strengths',
                icon: Icons.check_circle_outline,
                items: v2.explanation.strengths,
              ),
              _ExplanationSection(
                title: 'Gaps',
                icon: Icons.trending_up,
                items: v2.explanation.gaps,
              ),
              _ExplanationSection(
                title: 'Unknowns',
                icon: Icons.help_outline,
                items: v2.explanation.unknowns,
              ),
              _ExplanationSection(
                title: 'Preference conflicts',
                icon: Icons.warning_amber_outlined,
                items: v2.explanation.preferenceConflicts,
              ),
              if (v2.explanation.questions.isNotEmpty ||
                  v2.scores.questions.isNotEmpty)
                _QuestionPanel(
                  questions: {
                    ...v2.explanation.questions,
                    ...v2.scores.questions,
                  }.toList(),
                ),
            ] else if (rationale.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(rationale),
            ],
            const SizedBox(height: 16),
            _SnapshotPanel(
              title: 'Your profile used for this match',
              data: item.resumeData,
            ),
            _SnapshotPanel(title: 'Job profile', data: item.jobData),
            const Divider(height: 32),
            if (item.v2Result != null) ...[
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: _saving ? null : _rerun,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Run matching again'),
                ),
              ),
              const SizedBox(height: 16),
            ],
            Text(
              'How well does this job match you?',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            const Text(
              'Your feedback helps DaliJob tune future matching for you.',
            ),
            Semantics(
              label: 'Your match score',
              value: '${_score.round()} out of 100',
              child: Slider(
                value: _score,
                min: 0,
                max: 100,
                divisions: 20,
                label: '${_score.round()}',
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _score = value),
              ),
            ),
            Center(
              child: Text(
                '${_score.round()}/100 · ${_recommendation(_score.round())}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _rationale,
              enabled: !_saving,
              minLines: 2,
              maxLines: 5,
              maxLength: 4000,
              decoration: const InputDecoration(
                labelText: 'What looks right or wrong? (optional)',
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                key: const Key('save_match_feedback'),
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.rate_review_outlined),
                label: Text(
                  widget.item.userFeedback == null
                      ? 'Send feedback'
                      : 'Update feedback',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.repository.putMatchFeedback(
        matchId: widget.item.matchId,
        score: _score.round(),
        rationale: _rationale.text,
      );
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _rerun() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.repository.rerunMatchSchedule(widget.item.searchScheduleId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Matching started against the latest cached job profiles.',
            ),
          ),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class _ScoreSummary extends StatelessWidget {
  const _ScoreSummary({required this.item});

  final MatchInboxItem item;

  @override
  Widget build(BuildContext context) {
    final v2 = item.v2Result;
    if (v2 == null) {
      return Text(
        item.matchScore == null
            ? 'Score unavailable'
            : 'DaliJob score ${item.matchScore}/10',
        style: Theme.of(context).textTheme.titleMedium,
      );
    }
    final scores = v2.scores;
    final scoreText = scores.overallScore == null
        ? 'More information needed'
        : '${scores.overallScore}/100';
    return Card(
      color: scores.overallScore == null
          ? Theme.of(context).colorScheme.tertiaryContainer
          : Theme.of(context).colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(scoreText, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(_label(scores.recommendation)),
            const SizedBox(height: 8),
            Text(
              'Qualification ${_score(scores.qualificationScore)} '
              '· Coverage ${(scores.qualificationCoverage * 100).round()}% '
              '· Preferences ${_score(scores.preferenceScore)}',
            ),
            if (scores.reasonCodes.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: scores.reasonCodes
                    .map((code) => Chip(label: Text(_label(code))))
                    .toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ExplanationSection extends StatelessWidget {
  const _ExplanationSection({
    required this.title,
    required this.icon,
    required this.items,
  });

  final String title;
  final IconData icon;
  final List<V2ExplanationItem> items;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      leading: Icon(icon),
      title: Text('$title (${items.length})'),
      children: items
          .map(
            (item) => ListTile(
              contentPadding: const EdgeInsets.only(left: 8, right: 8),
              title: Text(item.label),
              subtitle: Text(item.detail),
              // Evidence identifiers are deliberately not rendered as links.
              // The API does not authorize source excerpts in this response.
            ),
          )
          .toList(),
    );
  }
}

class _QuestionPanel extends StatelessWidget {
  const _QuestionPanel({required this.questions});

  final List<String> questions;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Help improve this match',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 6),
          for (final question in questions)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text('• $question'),
            ),
        ],
      ),
    ),
  );
}

String _score(int? value) => value == null ? 'Not scored' : '$value/100';

String _label(String value) {
  final words = value.toLowerCase().split('_');
  if (words.isEmpty) return value;
  final text = words.join(' ');
  return '${text[0].toUpperCase()}${text.substring(1)}';
}

class _SnapshotPanel extends StatelessWidget {
  const _SnapshotPanel({required this.title, required this.data});

  final String title;
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    title: Text(title),
    children: [
      Align(
        alignment: Alignment.centerLeft,
        child: SelectableText(_readableSnapshot(data)),
      ),
      const SizedBox(height: 12),
    ],
  );
}

String _readableSnapshot(Map<String, dynamic> data) {
  if (data.isEmpty) return 'No snapshot was stored for this match.';
  return data.entries
      .where(
        (entry) =>
            entry.value != null && entry.value.toString().trim().isNotEmpty,
      )
      .map((entry) {
        final label = entry.key.replaceAll('_', ' ');
        final value = entry.value is List
            ? (entry.value as List).map((item) => item.toString()).join(', ')
            : entry.value.toString();
        return '$label: $value';
      })
      .join('\n\n');
}

String _recommendation(int score) {
  if (score >= 85) return 'Strong match';
  if (score >= 70) return 'Good match';
  if (score >= 55) return 'Consider';
  if (score >= 40) return 'Stretch';
  return 'Unlikely fit';
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
