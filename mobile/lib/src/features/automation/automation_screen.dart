import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../matching/matching_models.dart';
import '../../matching/matching_repository.dart';

class AutomationScreen extends StatefulWidget {
  const AutomationScreen({super.key, required this.repository});

  final MatchingRepository repository;

  @override
  State<AutomationScreen> createState() => _AutomationScreenState();
}

class _AutomationScreenState extends State<AutomationScreen> {
  OnboardingSnapshot? _snapshot;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final snapshot = await widget.repository.loadOnboarding();
      if (mounted) setState(() => _snapshot = snapshot);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = _snapshot;
    if (snapshot == null && _error == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (snapshot == null) {
      return _ErrorState(message: _error!, onRetry: _load);
    }

    final profile =
        snapshot.profiles.where((item) => item.isDefault).firstOrNull ??
        snapshot.profiles.firstOrNull;
    final criterion = snapshot.criteria.firstOrNull;
    final schedule = snapshot.schedules.firstOrNull;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          _EntitlementCard(entitlement: snapshot.entitlement),
          const SizedBox(height: 16),
          _SetupCard(
            step: 1,
            title: 'Resume',
            complete: profile != null,
            description: profile == null
                ? 'Upload your current resume or enter a quick profile.'
                : '${profile.title}${profile.isDefault ? ' · Default' : ''}',
            actions: profile == null
                ? [
                    FilledButton.tonalIcon(
                      onPressed: _busy ? null : _showLinkedInImport,
                      icon: const Icon(Icons.badge_outlined),
                      label: const Text('Import from LinkedIn'),
                    ),
                    OutlinedButton.icon(
                      onPressed: _busy ? null : _uploadResume,
                      icon: const Icon(Icons.upload_file),
                      label: const Text('Upload PDF/TXT'),
                    ),
                    TextButton(
                      onPressed: _busy ? null : _createManualResume,
                      child: const Text('Enter manually'),
                    ),
                  ]
                : const [],
          ),
          const SizedBox(height: 12),
          _SetupCard(
            step: 2,
            title: 'Job criteria',
            complete: criterion != null,
            description: criterion == null
                ? 'Tell DaliJob which role and location to search.'
                : '${criterion.keyword} · ${criterion.location ?? 'Any location'}',
            actions: profile != null && criterion == null
                ? [
                    FilledButton.tonalIcon(
                      onPressed: _busy ? null : () => _createCriterion(profile),
                      icon: const Icon(Icons.tune),
                      label: const Text('Add criteria'),
                    ),
                  ]
                : const [],
          ),
          const SizedBox(height: 12),
          _SetupCard(
            step: 3,
            title: 'Weekly matching',
            complete: schedule != null,
            description: schedule == null
                ? 'Enable automatic search and receive the best new match.'
                : schedule.enabled
                ? 'Active · Next run ${_formatDate(schedule.nextRunAt)}'
                : 'Paused${schedule.pausedReason == null ? '' : ' · ${schedule.pausedReason}'}',
            actions: profile != null && criterion != null && schedule == null
                ? [
                    FilledButton.icon(
                      onPressed: _busy
                          ? null
                          : () => _createSchedule(
                              profile,
                              criterion,
                              snapshot.entitlement,
                            ),
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('Enable matching'),
                    ),
                  ]
                : schedule != null
                ? [
                    SwitchListTile.adaptive(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Automatic matching'),
                      value: schedule.enabled,
                      onChanged: _busy
                          ? null
                          : (value) => _setEnabled(schedule, value),
                    ),
                    if (snapshot.entitlement.tierCode == 'super')
                      FilledButton.icon(
                        onPressed: _busy ? null : () => _runNow(schedule),
                        icon: const Icon(Icons.flash_on),
                        label: const Text('Run now'),
                      ),
                  ]
                : const [],
          ),
          if (_busy) ...[
            const SizedBox(height: 20),
            const Center(child: CircularProgressIndicator()),
          ],
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _uploadResume({bool linkedIn = false}) async {
    final file = await FilePicker.pickFile(
      type: FileType.custom,
      allowedExtensions: linkedIn ? const ['pdf'] : const ['pdf', 'docx', 'txt'],
    );
    if (file == null) return;
    final bytes = await file.readAsBytes();
    if (bytes.isEmpty) {
      setState(() => _error = 'The selected resume could not be read.');
      return;
    }
    await _run(
      () => widget.repository.uploadAndApplyResume(
        fileName: file.name,
        bytes: bytes,
        profileTitle: linkedIn ? 'LinkedIn Profile' : null,
      ),
    );
  }

  Future<void> _showLinkedInImport() async {
    final chooseFile = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Import from LinkedIn'),
        content: const Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'LinkedIn does not provide profile PDF export in its mobile app.',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            SizedBox(height: 12),
            Text(
              'Profile export: On a computer, open your LinkedIn profile, choose More or Resources, then Save to PDF. Transfer that PDF to this phone and select it here.',
            ),
            SizedBox(height: 12),
            Text(
              'Existing resume: On this phone, open LinkedIn Jobs → Preferences → Resumes and application data → More → Download.',
            ),
            SizedBox(height: 12),
            Text(
              'DaliJob imports only the PDF you select and never asks for your LinkedIn password.',
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () async {
              final opened = await launchUrl(
                Uri.parse(
                  'https://www.linkedin.com/jobs/application-settings/',
                ),
                mode: LaunchMode.externalApplication,
              );
              if (!opened && context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Could not open LinkedIn.')),
                );
              }
            },
            child: const Text('Open resume settings'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Choose PDF'),
          ),
        ],
      ),
    );
    if (chooseFile == true) await _uploadResume(linkedIn: true);
  }

  Future<void> _createManualResume() async {
    final values = await _showResumeDialog();
    if (values == null) return;
    await _run(
      () => widget.repository.createResumeProfile(
        title: values['title']!,
        headline: values['headline']!,
        summary: values['summary']!,
        skills: _split(values['skills']!),
        targetRoles: _split(values['roles']!),
      ),
    );
  }

  Future<void> _createCriterion(ResumeProfile profile) async {
    final values = await _showCriteriaDialog();
    if (values == null) return;
    await _run(
      () => widget.repository.createCriterion(
        resumeProfileId: profile.id,
        keyword: values['keyword']!,
        location: values['location']!,
      ),
    );
  }

  Future<void> _createSchedule(
    ResumeProfile profile,
    SearchCriterion criterion,
    Entitlement entitlement,
  ) async {
    await _run(
      () => widget.repository.createSchedule(
        criterion: criterion,
        profile: profile,
        entitlement: entitlement,
      ),
    );
  }

  Future<void> _setEnabled(SearchSchedule schedule, bool enabled) async {
    await _run(() => widget.repository.setScheduleEnabled(schedule, enabled));
  }

  Future<void> _runNow(SearchSchedule schedule) async {
    await _run(() => widget.repository.runScheduleNow(schedule));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Immediate matching run queued.')),
      );
    }
  }

  Future<void> _run(Future<Object> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      await _load();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<Map<String, String>?> _showResumeDialog() async {
    final title = TextEditingController(text: 'Master Resume');
    final headline = TextEditingController();
    final summary = TextEditingController();
    final roles = TextEditingController();
    final skills = TextEditingController();
    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Quick resume profile'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: title,
                decoration: const InputDecoration(labelText: 'Profile name'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: headline,
                decoration: const InputDecoration(
                  labelText: 'Professional headline',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: roles,
                decoration: const InputDecoration(
                  labelText: 'Target roles (comma separated)',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: skills,
                decoration: const InputDecoration(
                  labelText: 'Skills (comma separated)',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: summary,
                maxLines: 3,
                decoration: const InputDecoration(labelText: 'Summary'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (title.text.trim().isEmpty || roles.text.trim().isEmpty) {
                return;
              }
              Navigator.pop(context, {
                'title': title.text.trim(),
                'headline': headline.text.trim(),
                'summary': summary.text.trim(),
                'roles': roles.text.trim(),
                'skills': skills.text.trim(),
              });
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
    title.dispose();
    headline.dispose();
    summary.dispose();
    roles.dispose();
    skills.dispose();
    return result;
  }

  Future<Map<String, String>?> _showCriteriaDialog() async {
    final keyword = TextEditingController();
    final location = TextEditingController(text: 'Remote');
    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Job search criteria'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: keyword,
              decoration: const InputDecoration(labelText: 'Role or keywords'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: location,
              decoration: const InputDecoration(labelText: 'Location'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (keyword.text.trim().isEmpty || location.text.trim().isEmpty) {
                return;
              }
              Navigator.pop(context, {
                'keyword': keyword.text.trim(),
                'location': location.text.trim(),
              });
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
    keyword.dispose();
    location.dispose();
    return result;
  }

  List<String> _split(String value) => value
      .split(',')
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList();

  String _formatDate(DateTime value) {
    final local = value.toLocal();
    return '${local.month}/${local.day} at ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
  }
}

class _EntitlementCard extends StatelessWidget {
  const _EntitlementCard({required this.entitlement});
  final Entitlement entitlement;

  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.primaryContainer,
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          const Icon(Icons.bolt),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${entitlement.tierCode.toUpperCase()} plan',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                Text(
                  entitlement.searchesPerPeriod == null
                      ? 'Unlimited searches · internal testing'
                      : '${entitlement.searchesAvailable} of ${entitlement.searchesPerPeriod} searches available this week',
                ),
              ],
            ),
          ),
        ],
      ),
    ),
  );
}

class _SetupCard extends StatelessWidget {
  const _SetupCard({
    required this.step,
    required this.title,
    required this.complete,
    required this.description,
    required this.actions,
  });
  final int step;
  final String title;
  final bool complete;
  final String description;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 16,
                child: complete
                    ? const Icon(Icons.check, size: 18)
                    : Text('$step'),
              ),
              const SizedBox(width: 12),
              Text(title, style: Theme.of(context).textTheme.titleMedium),
            ],
          ),
          const SizedBox(height: 10),
          Text(description),
          if (actions.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(spacing: 8, runSpacing: 8, children: actions),
          ],
        ],
      ),
    ),
  );
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off, size: 48),
          const SizedBox(height: 12),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          FilledButton.tonal(
            onPressed: onRetry,
            child: const Text('Try again'),
          ),
        ],
      ),
    ),
  );
}
