import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../guest/guest_controller.dart';

class GuestTrialScreen extends StatefulWidget {
  const GuestTrialScreen({super.key, required this.controller});
  final GuestController controller;

  @override
  State<GuestTrialScreen> createState() => _GuestTrialScreenState();
}

class _GuestTrialScreenState extends State<GuestTrialScreen> {
  final _profileText = TextEditingController();
  final _role = TextEditingController();
  final _location = TextEditingController();
  bool _showProfileText = false;

  @override
  void initState() {
    super.initState();
    _loadExisting();
  }

  @override
  void dispose() {
    for (final controller in [_profileText, _role, _location]) {
      controller.dispose();
    }
    super.dispose();
  }

  void _loadExisting() {
    final snapshot = widget.controller.snapshot;
    final resumeData = snapshot?.profile?['resume_data'] is Map
        ? Map<String, dynamic>.from(snapshot!.profile!['resume_data'] as Map)
        : snapshot?.resumeImport?['suggestions'] is Map
        ? Map<String, dynamic>.from(
            snapshot!.resumeImport!['suggestions'] as Map,
          )
        : null;
    if (resumeData != null) {
      _profileText.text = _resumeDataAsText(resumeData);
    }
    _showProfileText = snapshot?.profile != null && snapshot?.isReady == false;
    _role.text = snapshot?.criteria?['keyword'] as String? ?? '';
    _location.text = snapshot?.criteria?['location'] as String? ?? '';
  }

  String _resumeDataAsText(Map<String, dynamic> data) => [
    data['headline']?.toString() ?? '',
    data['summary']?.toString() ?? '',
    ..._items(data['experience']),
    ..._items(data['projects']),
    ..._items(data['education']),
    if (_items(data['skills']).isNotEmpty)
      'Skills: ${_items(data['skills']).join(', ')}',
  ].where((item) => item.trim().isNotEmpty).join('\n\n');

  List<String> _items(Object? value) => value is List
      ? value
            .map((item) => item.toString())
            .where((item) => item.trim().isNotEmpty)
            .toList()
      : <String>[];

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.controller,
    builder: (context, _) {
      final snapshot = widget.controller.snapshot;
      final result = snapshot?.result;
      return Scaffold(
        appBar: AppBar(
          title: const Text('Try DaliJob'),
          actions: [
            TextButton(
              onPressed: widget.controller.busy
                  ? null
                  : widget.controller.leaveForSignIn,
              child: const Text('Sign in'),
            ),
            PopupMenuButton<String>(
              onSelected: (value) {
                if (value == 'delete') _confirmDelete();
              },
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'delete', child: Text('Delete my trial')),
              ],
            ),
          ],
        ),
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              const _PrivacyCard(),
              if (widget.controller.error != null) ...[
                const SizedBox(height: 12),
                Text(
                  widget.controller.error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 16),
              if (result != null)
                _resultView(result)
              else if (snapshot?.profile == null || snapshot?.isReady == false)
                _profileView()
              else if (snapshot?.criteria == null)
                _criteriaView()
              else
                _matchView(),
              if (widget.controller.busy) ...[
                const SizedBox(height: 20),
                const Center(child: CircularProgressIndicator()),
              ],
            ],
          ),
        ),
      );
    },
  );

  Widget _profileView() {
    final readiness = widget.controller.snapshot?.profile?['readiness'];
    final missing =
        readiness is Map && readiness['missing_requirements'] is List
        ? readiness['missing_requirements'] as List
        : const [];
    final imported = widget.controller.snapshot?.resumeImport;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Add your resume',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 8),
        const Text(
          'We use your experience, accomplishments, education, and skills to find jobs that truly match you.',
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: widget.controller.busy ? null : _pickResume,
          icon: const Icon(Icons.upload_file),
          label: const Text('Upload your resume'),
        ),
        const SizedBox(height: 8),
        TextButton(
          onPressed: widget.controller.busy
              ? null
              : () => setState(() => _showProfileText = true),
          child: const Text("Don't have a resume?"),
        ),
        if (imported?['parse_warning'] is String) ...[
          const SizedBox(height: 8),
          Text(imported!['parse_warning'] as String),
          TextButton(
            onPressed: widget.controller.busy
                ? null
                : widget.controller.retryAndConfirmResumeParse,
            child: const Text('Retry resume analysis'),
          ),
        ],
        if (missing.isNotEmpty) ...[
          const SizedBox(height: 8),
          const Text(
            'Add a little more detail for a better match:',
            style: TextStyle(fontWeight: FontWeight.w600),
          ),
          ...missing.map(
            (item) => ListTile(
              dense: true,
              leading: const Icon(Icons.info_outline),
              title: Text(item is Map ? item['message']?.toString() ?? '' : ''),
            ),
          ),
        ],
        if (_showProfileText) ...[
          const SizedBox(height: 16),
          const Text(
            'Tell us about your work, projects, education, accomplishments, and skills. The more detail you provide, the better your match will be.',
          ),
          const SizedBox(height: 10),
          TextField(
            key: const Key('guest_profile_text'),
            controller: _profileText,
            minLines: 8,
            maxLines: 14,
            decoration: const InputDecoration(
              labelText: 'Your background',
              alignLabelWithHint: true,
              hintText:
                  'Example: I worked in customer support for three years, trained new team members, improved response time, and regularly used Zendesk, Excel, and Salesforce...',
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: widget.controller.busy ? null : _useProfileText,
            child: const Text('Use this profile'),
          ),
        ],
      ],
    );
  }

  Widget _criteriaView() {
    final profile = widget.controller.snapshot?.profile?['resume_data'];
    final suggestedRoles = profile is Map
        ? _items(profile['target_roles']).take(5).toList()
        : <String>[];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Icon(Icons.check_circle, color: Colors.green, size: 48),
        Text(
          'Your profile is ready',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 8),
        const Text(
          'Choose a role suggested from your background, or enter a different one.',
          textAlign: TextAlign.center,
        ),
        if (suggestedRoles.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text(
            'Suggested roles',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: suggestedRoles
                .map(
                  (role) => ChoiceChip(
                    label: Text(role),
                    selected: _role.text == role,
                    onSelected: widget.controller.busy
                        ? null
                        : (_) => setState(() => _role.text = role),
                  ),
                )
                .toList(),
          ),
        ],
        const SizedBox(height: 20),
        TextField(
          controller: _role,
          decoration: InputDecoration(
            labelText: suggestedRoles.isEmpty
                ? 'Target role'
                : 'Or enter a different role',
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _location,
          decoration: const InputDecoration(
            labelText: 'Location',
            hintText: 'Remote or city, state',
          ),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: widget.controller.busy ? null : _saveCriteria,
          child: const Text('Continue to matching'),
        ),
      ],
    );
  }

  Widget _matchView() {
    final match = widget.controller.snapshot?.match;
    final retryable = match?['retryable'] == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Icon(
          retryable ? Icons.refresh : Icons.auto_awesome,
          size: 56,
          color: Theme.of(context).colorScheme.primary,
        ),
        const SizedBox(height: 12),
        Text(
          retryable
              ? 'Your search is safe to retry'
              : 'Get your best match now',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 8),
        Text(
          retryable
              ? 'A provider step failed, so no result was consumed. Retry uses the same saved profile and curated job catalog.'
              : 'Your trial runs immediately—there is no weekly wait. DaliJob compares your confirmed profile with quality-controlled job profiles already in its catalog and shows the best usable result.',
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 20),
        FilledButton.icon(
          onPressed: widget.controller.busy
              ? null
              : widget.controller.startMatch,
          icon: const Icon(Icons.search),
          label: Text(retryable ? 'Retry matching' : 'Match me now'),
        ),
      ],
    );
  }

  Widget _resultView(Map<String, dynamic> result) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text('Your best match', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 4),
      Text(
        result['result_context']?.toString() ??
            'Best usable match from this search',
      ),
      const SizedBox(height: 16),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  CircleAvatar(
                    radius: 25,
                    child: Text(
                      _v2Score(result)?['overall_score'] != null
                          ? '${_v2Score(result)!['overall_score']}/100'
                          : result['match_score'] == null
                          ? 'More\ninfo'
                          : '${result['match_score']}/10',
                      textAlign: TextAlign.center,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          result['title']?.toString() ?? '',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        Text(
                          '${result['company'] ?? ''} · ${result['location'] ?? ''}',
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Text(result['summary']?.toString() ?? ''),
              if (_v2Score(result) case final score?) ...[
                const SizedBox(height: 8),
                Text(
                  score['overall_score'] == null
                      ? 'More information needed · ${_guestLabel(score['recommendation'])}'
                      : '${_guestLabel(score['recommendation'])} · '
                            'Qualification ${score['qualification_score'] ?? 'not scored'} · '
                            'Coverage ${(((score['qualification_coverage'] as num?) ?? 0) * 100).round()}%',
                ),
                _chips('Questions to confirm', score['questions']),
              ],
              const SizedBox(height: 12),
              _chips('Matched skills', result['matched_skills']),
              _chips('Important gaps', result['missing_skills']),
              if (_v2Explanation(result) case final explanation?) ...[
                _chips('Unknowns', _explanationLabels(explanation['unknowns'])),
                _chips(
                  'Preference conflicts',
                  _explanationLabels(explanation['preference_conflicts']),
                ),
              ],
              if ((result['job_description']?.toString().trim() ?? '')
                  .isNotEmpty)
                ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  childrenPadding: const EdgeInsets.only(bottom: 12),
                  title: const Text('View job description'),
                  children: [
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(result['job_description'].toString()),
                    ),
                  ],
                ),
            ],
          ),
        ),
      ),
      const SizedBox(height: 16),
      Card(
        color: Theme.of(context).colorScheme.primaryContainer,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Get new matches automatically',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              const Text(
                'Create an account to set up saved profiles, weekly matching, and a private match inbox.',
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: widget.controller.leaveForRegistration,
                icon: const Icon(Icons.person_add_alt_1),
                label: const Text('Create an account'),
              ),
              TextButton(
                onPressed: widget.controller.leaveForSignIn,
                child: const Text('Already have an account? Sign in'),
              ),
            ],
          ),
        ),
      ),
    ],
  );

  Map<String, dynamic>? _v2Score(Map<String, dynamic> result) {
    final value = result['score'];
    return value is Map ? Map<String, dynamic>.from(value) : null;
  }

  Map<String, dynamic>? _v2Explanation(Map<String, dynamic> result) {
    final value = result['explanation'];
    return value is Map ? Map<String, dynamic>.from(value) : null;
  }

  List<String> _explanationLabels(Object? value) => value is List
      ? value
            .whereType<Map>()
            .map((item) => item['label']?.toString() ?? '')
            .where((item) => item.isNotEmpty)
            .toList()
      : const [];

  String _guestLabel(Object? value) {
    final text = value?.toString().replaceAll('_', ' ') ?? '';
    return text.isEmpty ? '' : '${text[0].toUpperCase()}${text.substring(1)}';
  }

  Widget _chips(String title, Object? values) {
    final items = _items(values);
    if (items.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: items.map((item) => Chip(label: Text(item))).toList(),
          ),
        ],
      ),
    );
  }

  Future<void> _pickResume() async {
    final file = await FilePicker.pickFile(
      type: FileType.custom,
      allowedExtensions: const ['pdf', 'docx', 'txt'],
    );
    if (file == null) return;
    final bytes = await file.readAsBytes();
    if (bytes.isEmpty) return;
    await widget.controller.importAndConfirmProfile(file.name, bytes);
  }

  Future<void> _useProfileText() async {
    final text = _profileText.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Tell us a little about your background.'),
        ),
      );
      return;
    }
    await widget.controller.importAndConfirmProfile(
      'profile.txt',
      utf8.encode(text),
    );
  }

  Future<void> _saveCriteria() async {
    if (_role.text.trim().isEmpty || _location.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter both a target role and location.')),
      );
      return;
    }
    await widget.controller.saveCriteria(
      _role.text.trim(),
      _location.text.trim(),
    );
  }

  Future<void> _confirmDelete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this trial?'),
        content: const Text(
          'Your uploaded resume, profile, criteria, and match will be permanently deleted.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed == true) await widget.controller.deleteTrial();
  }
}

class _PrivacyCard extends StatelessWidget {
  const _PrivacyCard();
  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.surfaceContainerHighest,
    child: const Padding(
      padding: EdgeInsets.all(14),
      child: Row(
        children: [
          Icon(Icons.lock_outline),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'No account required. Your private trial expires automatically and is used only for your requested match.',
            ),
          ),
        ],
      ),
    ),
  );
}
