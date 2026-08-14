import 'package:flutter/material.dart';

import '../../auth/session_controller.dart';
import '../../config/app_environment.dart';
import '../../matching/matching_repository.dart';
import '../automation/automation_screen.dart';
import '../matches/matches_screen.dart';

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
    final pages = [
      MatchesScreen(repository: _repository),
      AutomationScreen(repository: _repository),
      _AccountPage(session: widget.session, environment: widget.environment),
    ];
    return Scaffold(
      appBar: AppBar(title: Text(['Matches', 'Automation', 'Account'][_index])),
      body: pages[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.auto_awesome_outlined),
            selectedIcon: Icon(Icons.auto_awesome),
            label: 'Matches',
          ),
          NavigationDestination(
            icon: Icon(Icons.schedule_outlined),
            selectedIcon: Icon(Icons.schedule),
            label: 'Automation',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Account',
          ),
        ],
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
