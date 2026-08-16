import 'package:flutter/material.dart';

import '../../matching/matching_repository.dart';

enum _LabSection { candidate, job, matching }

class TesterEvaluationScreen extends StatefulWidget {
  const TesterEvaluationScreen({super.key, required this.repository});

  final MatchingRepository repository;

  @override
  State<TesterEvaluationScreen> createState() => _TesterEvaluationScreenState();
}

class _TesterEvaluationScreenState extends State<TesterEvaluationScreen> {
  Map<String, dynamic>? _catalog;
  List<Map<String, dynamic>>? _candidates;
  List<Map<String, dynamic>>? _jobs;
  Map<String, dynamic>? _candidateEvaluation;
  Map<String, dynamic>? _jobEvaluation;
  Map<String, dynamic>? _matchRun;
  int? _candidateProfileId;
  String? _jobSnapshotId;
  _LabSection _section = _LabSection.candidate;
  double _candidateScore = 50;
  double _jobScore = 50;
  double _matchScore = 50;
  final _candidateRationale = TextEditingController();
  final _jobRationale = TextEditingController();
  final _matchRationale = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _candidateRationale.dispose();
    _jobRationale.dispose();
    _matchRationale.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await widget.repository.loadTesterFixtures();
      final candidates = data.candidates;
      final jobs = data.jobs
          .where((item) => item['review_status'] == 'accepted')
          .toList();
      if (!mounted) return;
      setState(() {
        _catalog = data.catalog;
        _candidates = candidates;
        _jobs = jobs;
        _candidateProfileId = candidates.isEmpty
            ? null
            : candidates.first['resume_profile_id'] as int;
        _jobSnapshotId = jobs.isEmpty
            ? null
            : jobs.first['public_id'] as String;
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
    return ListView(
      key: const Key('tester_evaluation_lab'),
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Tester evaluation lab',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 4),
        const Text(
          'Review candidate extraction, job extraction, and matching as separate dependent stages.',
        ),
        const SizedBox(height: 16),
        SegmentedButton<_LabSection>(
          key: const Key('tester_lab_sections'),
          segments: const [
            ButtonSegment(
              value: _LabSection.candidate,
              icon: Icon(Icons.person_search_outlined),
              label: Text('Candidate'),
            ),
            ButtonSegment(
              value: _LabSection.job,
              icon: Icon(Icons.work_outline),
              label: Text('Job'),
            ),
            ButtonSegment(
              value: _LabSection.matching,
              icon: Icon(Icons.compare_arrows),
              label: Text('Matching'),
            ),
          ],
          selected: {_section},
          onSelectionChanged: _busy
              ? null
              : (value) => setState(() {
                  _section = value.single;
                  _error = null;
                }),
        ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Text(
            _error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        const SizedBox(height: 18),
        switch (_section) {
          _LabSection.candidate => _candidateSection(),
          _LabSection.job => _jobSection(),
          _LabSection.matching => _matchingSection(),
        },
      ],
    );
  }

  Widget _candidateSection() {
    final candidates = _candidates ?? const <Map<String, dynamic>>[];
    return Column(
      key: const Key('candidate_profile_lab'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Candidate Profile',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const Text(
          'Step 1: compare the resume source with its extracted Candidate Profile.',
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          key: const Key('tester_candidate_profile'),
          initialValue: _candidateProfileId,
          decoration: const InputDecoration(labelText: 'Candidate resume'),
          items: candidates
              .map(
                (item) => DropdownMenuItem<int>(
                  value: item['resume_profile_id'] as int,
                  child: Text(
                    _candidateLabel(item),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              )
              .toList(),
          onChanged: _busy
              ? null
              : (value) => setState(() {
                  _candidateProfileId = value;
                  _candidateEvaluation = null;
                }),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          key: const Key('load_candidate_profile_evaluation'),
          onPressed: _busy || _candidateProfileId == null
              ? null
              : _loadCandidateEvaluation,
          icon: const Icon(Icons.manage_search),
          label: Text(_busy ? 'Loading…' : 'Load or extract Candidate Profile'),
        ),
        if (_candidateEvaluation != null) ...[
          const SizedBox(height: 18),
          _TextPanel(
            title: 'Resume source',
            value:
                _candidateEvaluation!['resume_source']?['text'] as String? ??
                '',
          ),
          _JsonPanel(
            title: 'Candidate Profile',
            value: _candidateEvaluation!['candidate_profile'],
          ),
          _reviewPanel(
            stage: 'Candidate Profile',
            score: _candidateScore,
            controller: _candidateRationale,
            onScoreChanged: (value) => setState(() => _candidateScore = value),
            submitKey: const Key('submit_candidate_profile_review'),
            onSubmit: _submitCandidateReview,
          ),
        ],
      ],
    );
  }

  Widget _jobSection() {
    final jobs = _jobs ?? const <Map<String, dynamic>>[];
    return Column(
      key: const Key('job_profile_lab'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Job Profile', style: Theme.of(context).textTheme.titleLarge),
        const Text(
          'Step 2: compare the cached job description with its extracted Job Profile.',
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          key: const Key('tester_job_profile'),
          initialValue: _jobSnapshotId,
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
          onChanged: _busy
              ? null
              : (value) => setState(() {
                  _jobSnapshotId = value;
                  _jobEvaluation = null;
                }),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          key: const Key('load_job_profile_evaluation'),
          onPressed: _busy || _jobSnapshotId == null
              ? null
              : _loadJobEvaluation,
          icon: const Icon(Icons.manage_search),
          label: Text(_busy ? 'Loading…' : 'Load or extract Job Profile'),
        ),
        if (_jobEvaluation != null) ...[
          const SizedBox(height: 18),
          _TextPanel(
            title: 'Job description source',
            value: _jobEvaluation!['job_source']?['text'] as String? ?? '',
          ),
          _JsonPanel(
            title: 'Job Profile',
            value: _jobEvaluation!['job_profile'],
          ),
          _reviewPanel(
            stage: 'Job Profile',
            score: _jobScore,
            controller: _jobRationale,
            onScoreChanged: (value) => setState(() => _jobScore = value),
            submitKey: const Key('submit_job_profile_review'),
            onSubmit: _submitJobReview,
          ),
        ],
      ],
    );
  }

  Widget _matchingSection() {
    final candidates = _candidates ?? const <Map<String, dynamic>>[];
    final jobs = _jobs ?? const <Map<String, dynamic>>[];
    return Column(
      key: const Key('matching_lab'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Matching', style: Theme.of(context).textTheme.titleLarge),
        const Text(
          'Step 3: run a detailed assessment using cached Candidate and Job Profiles.',
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          key: const Key('tester_matching_candidate'),
          initialValue: _candidateProfileId,
          decoration: const InputDecoration(labelText: 'Candidate profile'),
          items: candidates
              .map(
                (item) => DropdownMenuItem<int>(
                  value: item['resume_profile_id'] as int,
                  child: Text(
                    _candidateLabel(item),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              )
              .toList(),
          onChanged: _busy
              ? null
              : (value) => setState(() => _candidateProfileId = value),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          key: const Key('tester_matching_job'),
          initialValue: _jobSnapshotId,
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
          onChanged: _busy
              ? null
              : (value) => setState(() => _jobSnapshotId = value),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          key: const Key('run_matching_evaluation'),
          onPressed:
              _busy || _candidateProfileId == null || _jobSnapshotId == null
              ? null
              : _runMatch,
          icon: const Icon(Icons.play_arrow),
          label: Text(_busy ? 'Running…' : 'Run selected match'),
        ),
        if (_matchRun != null) ...[
          const SizedBox(height: 18),
          Text(
            '${_matchRun!['job_company'] ?? ''} · ${_matchRun!['job_title'] ?? ''}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          _JsonPanel(
            title: 'Candidate Profile',
            value: _matchRun!['candidate_profile'],
          ),
          _JsonPanel(title: 'Job Profile', value: _matchRun!['job_profile']),
          _JsonPanel(
            title: 'Detailed match assessment',
            value: _matchRun!['qualification'],
          ),
          _reviewPanel(
            stage: 'Match',
            score: _matchScore,
            controller: _matchRationale,
            onScoreChanged: (value) => setState(() => _matchScore = value),
            submitKey: const Key('submit_tester_review'),
            onSubmit: _submitMatchReview,
          ),
        ],
      ],
    );
  }

  Widget _reviewPanel({
    required String stage,
    required double score,
    required TextEditingController controller,
    required ValueChanged<double> onScoreChanged,
    required Key submitKey,
    required Future<void> Function() onSubmit,
  }) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const Divider(height: 32),
      Text(
        '$stage review ${score.round()}/100',
        style: Theme.of(context).textTheme.titleMedium,
      ),
      Slider(
        value: score,
        min: 0,
        max: 100,
        divisions: 20,
        label: '${score.round()}',
        onChanged: _busy ? null : onScoreChanged,
      ),
      TextField(
        controller: controller,
        minLines: 2,
        maxLines: 5,
        onChanged: (_) => setState(() {}),
        decoration: const InputDecoration(labelText: 'Review rationale'),
      ),
      const SizedBox(height: 12),
      FilledButton.icon(
        key: submitKey,
        onPressed: _busy || controller.text.trim().isEmpty ? null : onSubmit,
        icon: const Icon(Icons.rate_review_outlined),
        label: const Text('Submit independent review'),
      ),
    ],
  );

  Future<void> _loadCandidateEvaluation() => _guard(() async {
    final result = await widget.repository.loadCandidateProfileEvaluation(
      _candidateProfileId!,
    );
    if (mounted) setState(() => _candidateEvaluation = result);
  });

  Future<void> _loadJobEvaluation() => _guard(() async {
    final result = await widget.repository.loadJobProfileEvaluation(
      _jobSnapshotId!,
    );
    if (mounted) setState(() => _jobEvaluation = result);
  });

  Future<void> _runMatch() => _guard(() async {
    final selected = (_candidates ?? const <Map<String, dynamic>>[]).firstWhere(
      (item) => item['resume_profile_id'] == _candidateProfileId,
    );
    final release = selected['fixture_group'] == 'synthetic'
        ? _catalog!['candidate_fixture_release'] as String
        : 'candidate-fixtures.internal.v1';
    final run = await widget.repository.startTesterEvaluation(
      resumeProfileId: _candidateProfileId!,
      jobSnapshotId: _jobSnapshotId!,
      candidateFixtureRelease: release,
    );
    if (mounted) setState(() => _matchRun = run);
  });

  Future<void> _submitCandidateReview() => _guard(() async {
    final profile = _candidateEvaluation!['candidate_profile'] as Map;
    await widget.repository.submitArtifactReview(
      stage: 'candidate_profile',
      artifactId: profile['candidate_profile_id'] as String,
      score: _candidateScore.round(),
      rationale: _candidateRationale.text,
    );
    _showSaved('Candidate Profile review saved.');
  });

  Future<void> _submitJobReview() => _guard(() async {
    final profile = _jobEvaluation!['job_profile'] as Map;
    await widget.repository.submitArtifactReview(
      stage: 'job_profile',
      artifactId: profile['job_profile_id'] as String,
      score: _jobScore.round(),
      rationale: _jobRationale.text,
    );
    _showSaved('Job Profile review saved.');
  });

  Future<void> _submitMatchReview() => _guard(() async {
    await widget.repository.submitTesterReview(
      runId: _matchRun!['public_id'] as String,
      score: _matchScore.round(),
      rationale: _matchRationale.text,
    );
    _showSaved('Matching review saved.');
  });

  Future<void> _guard(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _showSaved(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }
}

String _candidateLabel(Map<String, dynamic> item) {
  final group = item['fixture_group'] as String? ?? 'account';
  final prefix = switch (group) {
    'internal' => 'Real',
    'synthetic' => 'Synthetic',
    _ => 'Account',
  };
  return '$prefix · ${item['label'] ?? 'Candidate'}';
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

class _TextPanel extends StatelessWidget {
  const _TextPanel({required this.title, required this.value});

  final String title;
  final String value;

  @override
  Widget build(BuildContext context) => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    title: Text(title),
    children: [
      Align(alignment: Alignment.centerLeft, child: SelectableText(value)),
      const SizedBox(height: 12),
    ],
  );
}
