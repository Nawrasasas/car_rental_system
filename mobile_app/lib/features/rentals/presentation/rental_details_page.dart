import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../domain/rentals_repository.dart';

class RentalDetailsPage extends StatelessWidget {
  final int rentalId;
  const RentalDetailsPage({super.key, required this.rentalId});

  @override
  Widget build(BuildContext context) {
    final repo = context.read<RentalsRepository>();

    return Scaffold(
      appBar: AppBar(title: const Text('Rental Details')),
      body: FutureBuilder(
        future: repo.fetchRental(rentalId),
        builder: (context, snapshot) {
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final result = snapshot.data!;
          if (!result.isSuccess || result.data == null) return Center(child: Text(result.error ?? 'Failed'));
          final r = result.data!;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(r.contractNumber, style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              Text('Customer: ${r.customerName}'),
              Text('Vehicle: ${r.vehicleLabel}'),
              Text('Status: ${r.status}'),
              Text('Start: ${r.startDate}'),
              Text('End: ${r.endDate}'),
              Text('Net total: \$${r.netTotal.toStringAsFixed(2)}'),
            ],
          );
        },
      ),
    );
  }
}
