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
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => context.read<VehiclesController>().load());
  }

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<VehiclesController>();
    return Scaffold(
      appBar: AppBar(title: const Text('Vehicles')),
      body: ctrl.loading
          ? const Center(child: CircularProgressIndicator())
          : ctrl.error != null
              ? Center(child: Text(ctrl.error!))
              : ListView.builder(
                  itemCount: ctrl.vehicles.length,
                  itemBuilder: (context, index) {
                    final v = ctrl.vehicles[index];
                    return ListTile(
                      title: Text('${v.name} (${v.plateNumber})'),
                      subtitle: Text('Status: ${v.status}'),
                      trailing: Text('\$${v.dailyPrice.toStringAsFixed(2)}/day'),
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => VehicleDetailsPage(vehicleId: v.id)),
                      ),
                    );
                  },
                ),
    );
  }
}
