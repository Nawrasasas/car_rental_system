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
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => context.read<RentalsController>().load());
  }

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<RentalsController>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Rentals'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const CreateRentalPage())),
          )
        ],
      ),
      body: ctrl.loading
          ? const Center(child: CircularProgressIndicator())
          : ctrl.error != null
              ? Center(child: Text(ctrl.error!))
              : ListView.builder(
                  itemCount: ctrl.rentals.length,
                  itemBuilder: (context, index) {
                    final r = ctrl.rentals[index];
                    return ListTile(
                      title: Text(r.contractNumber),
                      subtitle: Text('${r.customerName} • ${r.vehicleLabel}'),
                      trailing: Text(r.status),
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => RentalDetailsPage(rentalId: r.id)),
                      ),
                    );
                  },
                ),
    );
  }
}
