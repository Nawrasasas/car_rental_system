import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'vehicle_details_page.dart';
import 'vehicles_controller.dart';

class VehiclesPage extends StatefulWidget {
  const VehiclesPage({super.key});

  @override
  State<VehiclesPage> createState() => _VehiclesPageState();
}

class _VehiclesPageState extends State<VehiclesPage> {
  final TextEditingController _searchController = TextEditingController();
  String _selectedStatus = 'All';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => context.read<VehiclesController>().load(),
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
      case 'available':
        return Colors.green.shade100;
      case 'rented':
        return Colors.red.shade100;
      case 'maintenance':
      case 'service':
        return Colors.orange.shade100;
      case 'internal_use':
        return Colors.blue.shade100;
      case 'sold':
      case 'out_of_service':
        return Colors.grey.shade300;
      case 'stolen':
        return Colors.purple.shade100;
      case 'accident':
        return Colors.deepOrange.shade100;
      default:
        return Colors.grey.shade200;
    }
  }

  Color _statusFg(String status) {
    switch (_normalize(status)) {
      case 'available':
        return Colors.green.shade900;
      case 'rented':
        return Colors.red.shade900;
      case 'maintenance':
      case 'service':
        return Colors.orange.shade900;
      case 'internal_use':
        return Colors.blue.shade900;
      case 'sold':
      case 'out_of_service':
        return Colors.grey.shade900;
      case 'stolen':
        return Colors.purple.shade900;
      case 'accident':
        return Colors.deepOrange.shade900;
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
    final ctrl = context.watch<VehiclesController>();

    final availableStatuses = [
      'All',
      ...ctrl.vehicles
          .map((v) => v.status.trim())
          .where((s) => s.isNotEmpty)
          .toSet()
          .toList()
        ..sort(),
    ];

    final filteredVehicles = ctrl.vehicles.where((v) {
      final query = _normalize(_searchController.text);

      final matchesSearch = query.isEmpty ||
          _normalize(v.name).contains(query) ||
          _normalize(v.plateNumber).contains(query) ||
          _normalize(v.status).contains(query);

      final matchesStatus =
          _selectedStatus == 'All' || v.status == _selectedStatus;

      return matchesSearch && matchesStatus;
    }).toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Vehicles'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<VehiclesController>().load(),
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
                    labelText: 'Search vehicles',
                    hintText: 'Name / plate number / status',
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
                'Results: ${filteredVehicles.length} / ${ctrl.vehicles.length}',
              ),
            ),
          ),
          Expanded(
            child: ctrl.loading
                ? const Center(child: CircularProgressIndicator())
                : ctrl.error != null
                    ? Center(child: Text(ctrl.error!))
                    : filteredVehicles.isEmpty
                        ? const Center(
                            child: Text('No vehicles match the selected filters.'),
                          )
                        : ListView.separated(
                            itemCount: filteredVehicles.length,
                            separatorBuilder: (_, __) => const Divider(height: 1),
                            itemBuilder: (context, index) {
                              final v = filteredVehicles[index];
                              return ListTile(
                                title: Text('${v.name} (${v.plateNumber})'),
                                subtitle: Text('\$${v.dailyPrice.toStringAsFixed(2)}/day'),
                                trailing: _statusChip(v.status),
                                onTap: () => Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => VehicleDetailsPage(vehicleId: v.id),
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