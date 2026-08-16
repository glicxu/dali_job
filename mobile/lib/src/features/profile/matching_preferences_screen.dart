import 'package:flutter/material.dart';

import '../../api/api_exception.dart';
import '../../matching/matching_models.dart';
import '../../matching/matching_repository.dart';

class MatchingPreferencesScreen extends StatefulWidget {
  const MatchingPreferencesScreen({super.key, required this.repository});

  final MatchingRepository repository;

  @override
  State<MatchingPreferencesScreen> createState() =>
      _MatchingPreferencesScreenState();
}

class _MatchingPreferencesScreenState extends State<MatchingPreferencesScreen> {
  final _roles = TextEditingController();
  final _locations = TextEditingController();
  final _country = TextEditingController(text: 'US');
  final _clearances = TextEditingController();
  final _travel = TextEditingController();
  PreferenceRevision? _preferences;
  EligibilityRevision? _eligibility;
  String _workplace = 'none';
  String _authorization = 'unknown';
  String _sponsorship = 'unknown';
  String _relocation = 'unknown';
  bool _loading = true;
  bool _saving = false;
  String? _message;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _roles.dispose();
    _locations.dispose();
    _country.dispose();
    _clearances.dispose();
    _travel.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final values = await Future.wait([
        widget.repository.getPreferences(),
        widget.repository.getEligibility(),
      ]);
      _preferences = values[0] as PreferenceRevision?;
      _eligibility = values[1] as EligibilityRevision?;
      _populate();
    } on ApiException catch (error) {
      if (mounted) setState(() => _message = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _populate() {
    final preferences = _preferences?.preferences ?? const <String, dynamic>{};
    _roles.text = _values(preferences['desired_roles']).join(', ');
    final locations = preferences['locations'];
    _locations.text = locations is Map
        ? _strings(locations['allowed']).join(', ')
        : '';
    final workplaces = preferences['workplace_types'];
    _workplace = workplaces is List && workplaces.isNotEmpty
        ? (workplaces.first as Map)['value']?.toString() ?? 'none'
        : 'none';

    final facts = _eligibility?.facts ?? const <String, dynamic>{};
    final authorizations = facts['work_authorizations'];
    if (authorizations is List && authorizations.isNotEmpty) {
      final authorization = authorizations.first as Map;
      _country.text = authorization['country']?.toString() ?? 'US';
      _authorization = authorization['status']?.toString() ?? 'unknown';
      final sponsorship = authorization['requires_sponsorship'];
      _sponsorship = sponsorship == null
          ? 'unknown'
          : sponsorship == true
          ? 'yes'
          : 'no';
    }
    _clearances.text = _strings(facts['clearances']).join(', ');
    _travel.text = facts['travel_availability_percent']?.toString() ?? '';
    _relocation = facts['relocation']?.toString() ?? 'unknown';
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _message = null;
    });
    try {
      final preferencePayload = Map<String, dynamic>.from(
        _preferences?.preferences ?? _emptyPreferences(),
      );
      preferencePayload['desired_roles'] = _csv(
        _roles.text,
      ).map((value) => {'value': value, 'importance': 'medium'}).toList();
      final locations = _csv(_locations.text);
      preferencePayload['locations'] = locations.isEmpty
          ? null
          : {
              'allowed': locations,
              'relocation': _relocation == 'unknown' ? 'maybe' : _relocation,
              'maximum_commute_minutes': null,
              'importance': 'medium',
            };
      preferencePayload['workplace_types'] = _workplace == 'none'
          ? <Object>[]
          : [
              {
                'value': _workplace,
                'preference': 'strongly_prefer',
                'importance': 'medium',
              },
            ];
      _preferences = await widget.repository.putPreferences(
        expectedRevision: _preferences?.revision ?? 0,
        preferences: preferencePayload,
      );

      final country = _country.text.trim().toUpperCase();
      final travel = double.tryParse(_travel.text.trim());
      final facts =
          Map<String, dynamic>.from(_eligibility?.facts ?? _emptyEligibility())
            ..['work_authorizations'] = country.length == 2
                ? [
                    {
                      'country': country,
                      'status': _authorization,
                      'requires_sponsorship': _sponsorship == 'unknown'
                          ? null
                          : _sponsorship == 'yes',
                    },
                  ]
                : <Object>[]
            ..['clearances'] = _csv(_clearances.text)
            ..['travel_availability_percent'] = travel
            ..['relocation'] = _relocation;
      _eligibility = await widget.repository.putEligibility(
        expectedRevision: _eligibility?.revision ?? 0,
        facts: facts,
      );
      if (mounted) setState(() => _message = 'Preferences saved.');
    } on ApiException catch (error) {
      if (error.statusCode == 409) {
        await _load();
        if (mounted) {
          setState(
            () => _message =
                'A newer revision was found. The latest values are loaded; review and save again.',
          );
        }
      } else if (mounted) {
        setState(() => _message = error.message);
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Match preferences')),
    body: _loading
        ? const Center(child: CircularProgressIndicator())
        : ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Text(
                'Preferences',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const Text(
                'Optional preferences improve matching but are not required for your first match.',
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _roles,
                decoration: const InputDecoration(
                  labelText: 'Desired roles',
                  hintText: 'Software Engineer, Technical Program Manager',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _locations,
                decoration: const InputDecoration(
                  labelText: 'Allowed locations',
                  hintText: 'Seattle, Remote',
                ),
              ),
              const SizedBox(height: 12),
              _dropdown(
                label: 'Workplace preference',
                value: _workplace,
                values: const ['none', 'remote', 'hybrid', 'onsite'],
                changed: (value) => setState(() => _workplace = value),
              ),
              const Divider(height: 40),
              Text(
                'Eligibility',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const Text(
                'Unknown answers remain unknown; they are never treated as a failure.',
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _country,
                maxLength: 2,
                decoration: const InputDecoration(labelText: 'Country code'),
              ),
              _dropdown(
                label: 'Work authorization',
                value: _authorization,
                values: const ['unknown', 'authorized', 'not_authorized'],
                changed: (value) => setState(() => _authorization = value),
              ),
              _dropdown(
                label: 'Requires sponsorship',
                value: _sponsorship,
                values: const ['unknown', 'yes', 'no'],
                changed: (value) => setState(() => _sponsorship = value),
              ),
              _dropdown(
                label: 'Open to relocation',
                value: _relocation,
                values: const ['unknown', 'yes', 'maybe', 'no'],
                changed: (value) => setState(() => _relocation = value),
              ),
              TextField(
                controller: _clearances,
                decoration: const InputDecoration(
                  labelText: 'Clearances (optional)',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _travel,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Travel availability percent',
                ),
              ),
              if (_message != null) ...[
                const SizedBox(height: 12),
                Text(_message!),
              ],
              const SizedBox(height: 20),
              FilledButton.icon(
                key: const Key('save_matching_preferences'),
                onPressed: _saving ? null : _save,
                icon: const Icon(Icons.save_outlined),
                label: Text(_saving ? 'Saving…' : 'Save'),
              ),
            ],
          ),
  );

  Widget _dropdown({
    required String label,
    required String value,
    required List<String> values,
    required ValueChanged<String> changed,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: DropdownButtonFormField<String>(
      initialValue: value,
      decoration: InputDecoration(labelText: label),
      items: values
          .map(
            (item) =>
                DropdownMenuItem(value: item, child: Text(_display(item))),
          )
          .toList(),
      onChanged: _saving ? null : (item) => changed(item!),
    ),
  );
}

Map<String, dynamic> _emptyPreferences() => {
  'desired_roles': <Object>[],
  'locations': null,
  'workplace_types': <Object>[],
  'compensation': null,
  'employment_types': null,
  'desired_skills': <Object>[],
  'avoided_industries': <Object>[],
  'hard_constraints': <Object>[],
};

Map<String, dynamic> _emptyEligibility() => {
  'work_authorizations': <Object>[],
  'clearances': null,
  'licenses': null,
  'travel_availability_percent': null,
  'relocation': 'unknown',
};

List<String> _csv(String value) => value
    .split(',')
    .map((item) => item.trim())
    .where((item) => item.isNotEmpty)
    .toList();

List<String> _strings(Object? value) =>
    value is List ? value.map((item) => item.toString()).toList() : const [];

List<String> _values(Object? value) => value is List
    ? value
          .whereType<Map>()
          .map((item) => item['value']?.toString() ?? '')
          .where((item) => item.isNotEmpty)
          .toList()
    : const [];

String _display(String value) => value
    .split('_')
    .map(
      (part) =>
          part.isEmpty ? part : '${part[0].toUpperCase()}${part.substring(1)}',
    )
    .join(' ');
