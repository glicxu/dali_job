import 'package:flutter/material.dart';

import '../../matching/matching_repository.dart';

class TesterEvaluationScreen extends StatefulWidget {
  const TesterEvaluationScreen({super.key, required this.repository});

  final MatchingRepository repository;

  @override
  State<TesterEvaluationScreen> createState() => _TesterEvaluationScreenState();
}

class _TesterEvaluationScreenState extends State<TesterEvaluationScreen> {
  Map<String, dynamic>? _catalog;
  List<Map<String, dynamic>>? _jobs;
  Map<String, dynamic>? _run;
  int? _profileId;
  String? _jobId;
  double _score = 50;
  final _rationale = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _rationale.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await widget.repository.loadTesterFixtures();
      final candidates = (data.catalog['candidates'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .where(
            (item) =>
                item['loaded'] == true && item['resume_profile_id'] is int,
          )
          .toList();
      final jobs = data.jobs
          .where((item) => item['review_status'] == 'accepted')
          .toList();
      if (!mounted) return;
      setState(() {
        _catalog = {...data.catalog, 'candidates': candidates};
        _jobs = jobs;
        _profileId = candidates.isEmpty
            ? null
            : candidates.first['resume_profile_id'] as int;
        _jobId = jobs.isEmpty ? null : jobs.first['public_id'] as String;
        _error = null;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_catalog == null && _error == null) {
      return const Center(child: CircularProgressIndicator());
    }
    final candidates = (_catalog?['candidates'] as List? ?? const [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    final jobs = _jobs ?? const <Map<String, dynamic>>[];
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Tester match lab',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 4),
        const Text(
          'Admin-only access to frozen candidate profiles and benchmark jobs.',
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<int>(
          key: const Key('tester_candidate_profile'),
          initialValue: _profileId,
          decoration: const InputDecoration(labelText: 'Candidate profile'),
          items: candidates
              .map(
                (item) => DropdownMenuItem<int>(
                  value: item['resume_profile_id'] as int,
                  child: Text(item['label'] as String? ?? 'Candidate fixture'),
                ),
              )
              .toList(),
          onChanged: _busy
              ? null
              : (value) => setState(() => _profileId = value),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          key: const Key('tester_job_profile'),
          initialValue: _jobId,
          decoration: const InputDecoration(labelText: 'Benchmark job'),
          items: jobs
              .map(
                (item) => DropdownMenuItem<String>(
                  value: item['public_id'] as String,
                  child: Text(
                    '${item['company'] ?? ''} · ${item['title'] ?? 'Job'}',
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              )
              .toList(),
          onChanged: _busy ? null : (value) => setState(() => _jobId = value),
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: _busy || _profileId == null || _jobId == null
              ? null
              : _runMatch,
          icon: const Icon(Icons.play_arrow),
          label: Text(_busy ? 'Running…' : 'Run selected match'),
        ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Text(
            _error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        if (_run != null) ...[
          const SizedBox(height: 24),
          Text(
            '${_run!['job_company'] ?? ''} · ${_run!['job_title'] ?? ''}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          _JsonPanel(
            title: 'Candidate profile',
            value: _run!['candidate_profile'],
          ),
          _JsonPanel(title: 'Job profile', value: _run!['job_profile']),
          _JsonPanel(
            title: 'Detailed match assessment',
            value: _run!['qualification'],
          ),
          const Divider(height: 32),
          Text(
            'Human review ${_score.round()}/100',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          Slider(
            value: _score,
            min: 0,
            max: 100,
            divisions: 20,
            label: '${_score.round()}',
            onChanged: _busy ? null : (value) => setState(() => _score = value),
          ),
          TextField(
            controller: _rationale,
            minLines: 2,
            maxLines: 5,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(labelText: 'Review rationale'),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            key: const Key('submit_tester_review'),
            onPressed: _busy || _rationale.text.trim().isEmpty
                ? null
                : _submitReview,
            icon: const Icon(Icons.rate_review_outlined),
            label: const Text('Submit independent review'),
          ),
        ],
      ],
    );
  }

  Future<void> _runMatch() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final run = await widget.repository.startTesterEvaluation(
        resumeProfileId: _profileId!,
        jobSnapshotId: _jobId!,
        candidateFixtureRelease:
            _catalog!['candidate_fixture_release'] as String,
      );
      if (mounted) setState(() => _run = run);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submitReview() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.repository.submitTesterReview(
        runId: _run!['public_id'] as String,
        score: _score.round(),
        rationale: _rationale.text,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Independent review saved.')),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}

class _JsonPanel extends StatelessWidget {
  const _JsonPanel({required this.title, required this.value});

  final String title;
  final Object? value;

  @override
  Widget build(BuildContext context) => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    title: Text(title),
    children: [
      Align(
        alignment: Alignment.centerLeft,
        child: SelectableText(value.toString()),
      ),
      const SizedBox(height: 12),
    ],
  );
}
