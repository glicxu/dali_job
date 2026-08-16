import 'package:flutter/material.dart';

import '../../matching/matching_models.dart';
import '../../matching/matching_repository.dart';
import '../../api/api_exception.dart';
import 'matching_preferences_screen.dart';

class CandidateProfilesScreen extends StatefulWidget {
  const CandidateProfilesScreen({super.key, required this.repository});

  final MatchingRepository repository;

  @override
  State<CandidateProfilesScreen> createState() =>
      _CandidateProfilesScreenState();
}

class _CandidateProfilesScreenState extends State<CandidateProfilesScreen> {
  late Future<List<ResumeProfile>> _profiles;

  @override
  void initState() {
    super.initState();
    _profiles = widget.repository.listResumeProfiles();
  }

  Future<void> _reload() async {
    final profiles = widget.repository.listResumeProfiles();
    setState(() => _profiles = profiles);
    await profiles;
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<ResumeProfile>>(
    future: _profiles,
    builder: (context, snapshot) {
      if (snapshot.connectionState != ConnectionState.done) {
        return const Center(child: CircularProgressIndicator());
      }
      if (snapshot.hasError) {
        return _ProfileMessage(
          icon: Icons.cloud_off_outlined,
          title: 'Candidate profile unavailable',
          message: 'Pull to retry or check the server connection.',
          onRefresh: _reload,
        );
      }
      final profiles = snapshot.data ?? const <ResumeProfile>[];
      if (profiles.isEmpty) {
        return _ProfileMessage(
          icon: Icons.description_outlined,
          title: 'No candidate profile yet',
          message:
              'Upload a resume from Automation. Your extracted profile will appear here for review.',
          onRefresh: _reload,
        );
      }
      return RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          key: const Key('candidate_profiles_screen'),
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Candidate profiles',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                ),
                IconButton(
                  tooltip: 'Match preferences and eligibility',
                  icon: const Icon(Icons.tune),
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => MatchingPreferencesScreen(
                        repository: widget.repository,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              'Check what DaliJob currently knows before it evaluates job matches.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            for (final profile in profiles)
              Card(
                child: ListTile(
                  key: Key('candidate_profile_${profile.id}'),
                  leading: const CircleAvatar(
                    child: Icon(Icons.description_outlined),
                  ),
                  title: Text(profile.title),
                  subtitle: Text(_profileSubtitle(profile)),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (profile.isDefault)
                        const Padding(
                          padding: EdgeInsets.only(right: 8),
                          child: Chip(label: Text('Default')),
                        ),
                      const Icon(Icons.chevron_right),
                    ],
                  ),
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => CandidateProfileDetails(
                        profile: profile,
                        repository: widget.repository,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      );
    },
  );
}

class CandidateProfileDetails extends StatefulWidget {
  const CandidateProfileDetails({
    super.key,
    required this.profile,
    required this.repository,
  });

  final ResumeProfile profile;
  final MatchingRepository repository;

  @override
  State<CandidateProfileDetails> createState() =>
      _CandidateProfileDetailsState();
}

class _CandidateProfileDetailsState extends State<CandidateProfileDetails> {
  CandidateProfileV2? _candidate;
  bool _loadingCareer = true;
  bool _savingCareer = false;

  @override
  void initState() {
    super.initState();
    _loadCareer();
  }

  Future<void> _loadCareer() async {
    try {
      final candidate = await widget.repository.getCandidateProfile(
        widget.profile.id,
      );
      if (mounted) setState(() => _candidate = candidate);
    } on ApiException {
      if (mounted) setState(() => _candidate = null);
    } finally {
      if (mounted) setState(() => _loadingCareer = false);
    }
  }

  Future<void> _confirmCareer(String careerProfileId) async {
    final current = _candidate;
    if (current == null) return;
    setState(() => _savingCareer = true);
    try {
      final updated = await widget.repository.confirmCareerProfile(
        profile: current,
        careerProfileId: careerProfileId,
      );
      if (mounted) setState(() => _candidate = updated);
    } on ApiException catch (error) {
      if (error.statusCode == 409) {
        await _loadCareer();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'This profile changed elsewhere. Refreshed the latest selection; please retry.',
              ),
            ),
          );
        }
      } else {
        rethrow;
      }
    } finally {
      if (mounted) setState(() => _savingCareer = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final profile = widget.profile;
    final data = profile.resumeData;
    final headline = _text(data['headline']);
    final summary = _text(data['summary']);
    final sections = <(String, IconData, List<String>)>[
      ('Target roles', Icons.flag_outlined, _items(data['target_roles'])),
      ('Skills', Icons.construction_outlined, _items(data['skills'])),
      ('Experience', Icons.work_outline, _items(data['experience'])),
      ('Projects', Icons.rocket_launch_outlined, _items(data['projects'])),
      ('Education', Icons.school_outlined, _items(data['education'])),
      (
        'Certifications',
        Icons.workspace_premium_outlined,
        _items(data['certifications']),
      ),
      ('Publications', Icons.menu_book_outlined, _items(data['publications'])),
      ('Awards', Icons.emoji_events_outlined, _items(data['awards'])),
      ('Languages', Icons.translate_outlined, _items(data['languages'])),
      (
        'Volunteer',
        Icons.volunteer_activism_outlined,
        _items(data['volunteer']),
      ),
      ('Review notes', Icons.info_outline, _items(data['notes'])),
    ];

    return Scaffold(
      appBar: AppBar(title: const Text('Candidate profile')),
      body: ListView(
        key: const Key('candidate_profile_details'),
        padding: const EdgeInsets.all(20),
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  profile.title,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ),
              if (profile.isDefault) const Chip(label: Text('Default')),
            ],
          ),
          if (headline != null) ...[
            const SizedBox(height: 8),
            Text(headline, style: Theme.of(context).textTheme.titleMedium),
          ],
          if (summary != null) ...[const SizedBox(height: 12), Text(summary)],
          const SizedBox(height: 20),
          _CareerProfileCard(
            candidate: _candidate,
            loading: _loadingCareer,
            saving: _savingCareer,
            onConfirm: _confirmCareer,
          ),
          const SizedBox(height: 12),
          for (final section in sections)
            if (section.$3.isNotEmpty)
              _ProfileSection(
                title: section.$1,
                icon: section.$2,
                items: section.$3,
              ),
        ],
      ),
    );
  }
}

class _CareerProfileCard extends StatelessWidget {
  const _CareerProfileCard({
    required this.candidate,
    required this.loading,
    required this.saving,
    required this.onConfirm,
  });

  final CandidateProfileV2? candidate;
  final bool loading;
  final bool saving;
  final Future<void> Function(String) onConfirm;

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: LinearProgressIndicator(),
        ),
      );
    }
    if (candidate == null) {
      return const Card(
        child: ListTile(
          leading: Icon(Icons.auto_awesome_outlined),
          title: Text('Career level and track not generated yet'),
          subtitle: Text(
            'Your first supported match can generate this profile automatically.',
          ),
        ),
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Career level and track',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            const Text(
              'Optional: confirm the profile DaliJob should use as the primary matching context.',
            ),
            const SizedBox(height: 10),
            RadioGroup<String>(
              groupValue: candidate!.primaryCareerProfileId,
              onChanged: saving
                  ? (_) {}
                  : (value) {
                      if (value != null) onConfirm(value);
                    },
              child: Column(
                children: [
                  for (final career in candidate!.careerProfiles)
                    RadioListTile<String>(
                      key: Key('career_profile_${career.id}'),
                      contentPadding: EdgeInsets.zero,
                      value: career.id,
                      enabled: !saving,
                      title: Text(
                        '${_display(career.roleFamily)} · ${_display(career.level)}',
                      ),
                      subtitle: Text(
                        '${_display(career.track)} track · ${(career.confidence * 100).round()}% confidence',
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _display(String value) => value
    .split('_')
    .map(
      (part) =>
          part.isEmpty ? part : '${part[0].toUpperCase()}${part.substring(1)}',
    )
    .join(' ');

class _ProfileSection extends StatelessWidget {
  const _ProfileSection({
    required this.title,
    required this.icon,
    required this.items,
  });

  final String title;
  final IconData icon;
  final List<String> items;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 20),
              const SizedBox(width: 8),
              Text(title, style: Theme.of(context).textTheme.titleMedium),
            ],
          ),
          const SizedBox(height: 10),
          for (final item in items)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(top: 7),
                    child: Icon(Icons.circle, size: 6),
                  ),
                  const SizedBox(width: 8),
                  Expanded(child: Text(item)),
                ],
              ),
            ),
        ],
      ),
    ),
  );
}

class _ProfileMessage extends StatelessWidget {
  const _ProfileMessage({
    required this.icon,
    required this.title,
    required this.message,
    required this.onRefresh,
  });

  final IconData icon;
  final String title;
  final String message;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: onRefresh,
    child: ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 80),
      children: [
        Icon(icon, size: 56, color: Theme.of(context).colorScheme.primary),
        const SizedBox(height: 16),
        Text(
          title,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 8),
        Text(message, textAlign: TextAlign.center),
      ],
    ),
  );
}

String? _text(Object? value) {
  final text = value is String ? value.trim() : '';
  return text.isEmpty ? null : text;
}

List<String> _items(Object? value) => value is List
    ? value
          .whereType<Object>()
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList()
    : const [];

String _profileSubtitle(ResumeProfile profile) {
  final headline = _text(profile.resumeData['headline']);
  if (headline != null) return headline;
  final skills = _items(profile.resumeData['skills']);
  if (skills.isNotEmpty) return '${skills.length} skills captured';
  return 'Open to review extracted details';
}
