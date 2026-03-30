import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'create_rental_page.dart';
import 'rental_details_page.dart';
import 'rentals_controller.dart';

class RentalsPage extends StatefulWidget {
  const RentalsPage({super.key});

  @override
  State<RentalsPage> createState() => _RentalsPageState();
}

class _RentalsPageState extends State<RentalsPage> {
  final TextEditingController _searchController = TextEditingController();
  String _selectedStatus = 'All';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => context.read<RentalsController>().load(),
    );
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  String _normalize(String value) => value.trim().toLowerCase();

  Color _statusBg(String status) {
    switch (_normalize(status)) {
      case 'active':
        return Colors.blue.shade100;
      case 'completed':
        return Colors.green.shade100;
      case 'cancelled':
        return Colors.red.shade100;
      case 'overdue':
        return Colors.orange.shade100;
      default:
        return Colors.grey.shade200;
    }
  }

  Color _statusFg(String status) {
    switch (_normalize(status)) {
      case 'active':
        return Colors.blue.shade900;
      case 'completed':
        return Colors.green.shade900;
      case 'cancelled':
        return Colors.red.shade900;
      case 'overdue':
        return Colors.orange.shade900;
      default:
        return Colors.grey.shade800;
    }
  }

  Widget _statusChip(String status) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: _statusBg(status),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        status,
        style: TextStyle(
          color: _statusFg(status),
          fontWeight: FontWeight.w700,
          fontSize: 12,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<RentalsController>();

    final availableStatuses = [
      'All',
      ...ctrl.rentals
          .map((r) => r.status.trim())
          .where((s) => s.isNotEmpty)
          .toSet()
          .toList()
        ..sort(),
    ];

    final filteredRentals = ctrl.rentals.where((r) {
      final query = _normalize(_searchController.text);

      final matchesSearch = query.isEmpty ||
          _normalize(r.contractNumber).contains(query) ||
          _normalize(r.customerName).contains(query) ||
          _normalize(r.vehicleLabel).contains(query) ||
          _normalize(r.status).contains(query);

      final matchesStatus =
          _selectedStatus == 'All' || r.status == _selectedStatus;

      return matchesSearch && matchesStatus;
    }).toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Rentals'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<RentalsController>().load(),
          ),
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const CreateRentalPage()),
            ).then((_) {
              if (mounted) {
                context.read<RentalsController>().load();
              }
            }),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
            child: Column(
              children: [
                TextField(
                  controller: _searchController,
                  onChanged: (_) => setState(() {}),
                  decoration: InputDecoration(
                    labelText: 'Search contracts',
                    hintText: 'Contract / customer / vehicle / status',
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: _searchController.text.isEmpty
                        ? null
                        : IconButton(
                            icon: const Icon(Icons.clear),
                            onPressed: () {
                              _searchController.clear();
                              setState(() {});
                            },
                          ),
                    border: const OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  value: availableStatuses.contains(_selectedStatus)
                      ? _selectedStatus
                      : 'All',
                  items: availableStatuses
                      .map(
                        (status) => DropdownMenuItem<String>(
                          value: status,
                          child: Text(status),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    setState(() {
                      _selectedStatus = value ?? 'All';
                    });
                  },
                  decoration: const InputDecoration(
                    labelText: 'Filter by status',
                    border: OutlineInputBorder(),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Results: ${filteredRentals.length} / ${ctrl.rentals.length}',
              ),
            ),
          ),
          Expanded(
            child: ctrl.loading
                ? const Center(child: CircularProgressIndicator())
                : ctrl.error != null
                    ? Center(child: Text(ctrl.error!))
                    : filteredRentals.isEmpty
                        ? const Center(
                            child: Text('No rentals match the selected filters.'),
                          )
                        : ListView.separated(
                            itemCount: filteredRentals.length,
                            separatorBuilder: (_, __) => const Divider(height: 1),
                            itemBuilder: (context, index) {
                              final r = filteredRentals[index];
                              return ListTile(
                                title: Text(r.contractNumber),
                                subtitle: Text('${r.customerName} • ${r.vehicleLabel}'),
                                trailing: _statusChip(r.status),
                                onTap: () => Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => RentalDetailsPage(rentalId: r.id),
                                  ),
                                ),
                              );
                            },
                          ),
          ),
        ],
      ),
    );
  }
}