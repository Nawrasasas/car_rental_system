import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/network/api_client.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../rentals/presentation/rentals_page.dart';
import '../../vehicles/presentation/vehicles_page.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  bool loading = true;
  String? error;

  int activeRentals = 0;
  int overdueRentals = 0;
  double monthlyRevenue = 0;

  @override
  void initState() {
    super.initState();
    _loadSummaryFromRentals();
  }

  Future<void> _loadSummaryFromRentals() async {
    setState(() {
      loading = true;
      error = null;
    });

    try {
      final api = context.read<ApiClient>();
      final response = await api.get('/rentals/');
      final raw = (response['results'] ?? []) as List<dynamic>;

      final now = DateTime.now();

      int activeCount = 0;
      int overdueCount = 0;
      double revenueThisMonth = 0;

      for (final item in raw) {
        final rental = item as Map<String, dynamic>;

        final status = (rental['status']?.toString() ?? '').trim().toLowerCase();
        final startDateRaw = rental['start_date']?.toString() ?? '';
        final netTotalRaw = rental['net_total']?.toString() ?? '0';

        if (status == 'active' || status == 'overdue') {
          activeCount += 1;
        }

        if (status == 'overdue') {
          overdueCount += 1;
        }

        DateTime? startDate;
        if (startDateRaw.isNotEmpty) {
          startDate = DateTime.tryParse(startDateRaw.replaceFirst(' ', 'T'));
        }

        if (startDate != null &&
            startDate.year == now.year &&
            startDate.month == now.month) {
          revenueThisMonth += double.tryParse(netTotalRaw) ?? 0;
        }
      }

      setState(() {
        activeRentals = activeCount;
        overdueRentals = overdueCount;
        monthlyRevenue = revenueThisMonth;
        loading = false;
      });
    } catch (e) {
      setState(() {
        error = e.toString().replaceFirst('Exception: ', '');
        loading = false;
      });
    }
  }

  Color _cardColor(int index) {
    switch (index) {
      case 0:
        return Colors.blue.shade50;
      case 1:
        return Colors.green.shade50;
      case 2:
        return Colors.orange.shade50;
      default:
        return Colors.grey.shade100;
    }
  }

  IconData _cardIcon(int index) {
    switch (index) {
      case 0:
        return Icons.receipt_long;
      case 1:
        return Icons.attach_money;
      case 2:
        return Icons.warning_amber_rounded;
      default:
        return Icons.info_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Dashboard'),
        actions: [
          IconButton(
            onPressed: _loadSummaryFromRentals,
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            onPressed: () => context.read<AuthController>().logout(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            const Text(
              'MVP Overview',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            if (loading) const LinearProgressIndicator(),
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  'Summary load error: $error',
                  style: const TextStyle(color: Colors.orange),
                ),
              ),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                _metricCard(
                  title: 'Active Rentals',
                  value: activeRentals.toString(),
                  index: 0,
                ),
                _metricCard(
                  title: 'Revenue (Month)',
                  value: monthlyRevenue.toStringAsFixed(2),
                  index: 1,
                ),
                _metricCard(
                  title: 'Overdue Rentals',
                  value: overdueRentals.toString(),
                  index: 2,
                ),
              ],
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const VehiclesPage()),
              ),
              icon: const Icon(Icons.directions_car),
              label: const Text('Vehicles List'),
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const RentalsPage()),
              ),
              icon: const Icon(Icons.receipt_long),
              label: const Text('Rentals List'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _metricCard({
    required String title,
    required String value,
    required int index,
  }) {
    return SizedBox(
      width: 180,
      child: Card(
        color: _cardColor(index),
        elevation: 1,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(_cardIcon(index), size: 20),
              const SizedBox(height: 8),
              Text(
                title,
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                value,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}