import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../domain/vehicle.dart';
import '../domain/vehicles_repository.dart';

class VehicleDetailsPage extends StatelessWidget {
  final int vehicleId;
  const VehicleDetailsPage({super.key, required this.vehicleId});

  @override
  Widget build(BuildContext context) {
    final repo = context.read<VehiclesRepository>();
    return Scaffold(
      appBar: AppBar(title: const Text('Vehicle Details')),
      body: FutureBuilder(
        future: repo.fetchVehicle(vehicleId),
        builder: (context, snapshot) {
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final result = snapshot.data!;
          if (!result.isSuccess || result.data == null) {
            return Center(child: Text(result.error ?? 'Failed to load'));
          }
          final Vehicle vehicle = result.data!;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(vehicle.name, style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              Text('Plate: ${vehicle.plateNumber}'),
              Text('Status: ${vehicle.status}'),
              Text('Daily Price: \$${vehicle.dailyPrice.toStringAsFixed(2)}'),
            ],
          );
        },
      ),
    );
  }
}
