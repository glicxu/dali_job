import 'package:flutter/material.dart';

import '../../auth/session_controller.dart';
import '../../config/app_environment.dart';
import '../../matching/matching_repository.dart';
import '../automation/automation_screen.dart';
import '../evaluation/tester_evaluation_screen.dart';
import '../matches/matches_screen.dart';
import '../profile/candidate_profiles_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.session,
    required this.environment,
  });

  final SessionController session;
  final AppEnvironment environment;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;
  late final MatchingRepository _repository;

  @override
  void initState() {
    super.initState();
    _repository = MatchingRepository(
      widget.session.repository.api,
      widget.session,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isTester = widget.session.user?.role == 'admin';
    final pages = [
      MatchesScreen(repository: _repository),
      AutomationScreen(repository: _repository),
      CandidateProfilesScreen(repository: _repository),
      if (isTester) TesterEvaluationScreen(repository: _repository),
      _AccountPage(session: widget.session, environment: widget.environment),
    ];
    final titles = [
      'Matches',
      'Automation',
      'Profile',
      if (isTester) 'Test lab',
      'Account',
    ];
    final destinations = [
      const NavigationDestination(
        icon: Icon(Icons.auto_awesome_outlined),
        selectedIcon: Icon(Icons.auto_awesome),
        label: 'Matches',
      ),
      const NavigationDestination(
        icon: Icon(Icons.schedule_outlined),
        selectedIcon: Icon(Icons.schedule),
        label: 'Automation',
      ),
      const NavigationDestination(
        icon: Icon(Icons.badge_outlined),
        selectedIcon: Icon(Icons.badge),
        label: 'Profile',
      ),
      if (isTester)
        const NavigationDestination(
          icon: Icon(Icons.science_outlined),
          selectedIcon: Icon(Icons.science),
          label: 'Test lab',
        ),
      const NavigationDestination(
        icon: Icon(Icons.person_outline),
        selectedIcon: Icon(Icons.person),
        label: 'Account',
      ),
    ];
    return Scaffold(
      appBar: AppBar(title: Text(titles[_index])),
      body: pages[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: destinations,
      ),
    );
  }
}

class _AccountPage extends StatelessWidget {
  const _AccountPage({required this.session, required this.environment});
  final SessionController session;
  final AppEnvironment environment;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(24),
    children: [
      CircleAvatar(
        radius: 36,
        child: Text(session.user!.displayName.characters.first.toUpperCase()),
      ),
      const SizedBox(height: 16),
      Text(
        session.user!.displayName,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.titleLarge,
      ),
      Text(session.user!.email, textAlign: TextAlign.center),
      const SizedBox(height: 32),
      ListTile(
        leading: const Icon(Icons.cloud_outlined),
        title: const Text('Environment'),
        subtitle: Text(environment.name),
      ),
      const SizedBox(height: 16),
      OutlinedButton.icon(
        onPressed: session.signOut,
        icon: const Icon(Icons.logout),
        label: const Text('Sign out'),
      ),
    ],
  );
}
