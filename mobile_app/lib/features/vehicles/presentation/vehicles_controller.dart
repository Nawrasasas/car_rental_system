import 'package:flutter/material.dart';

import '../domain/vehicle.dart';
import '../domain/vehicles_repository.dart';

class VehiclesController extends ChangeNotifier {
  final VehiclesRepository repository;
  VehiclesController(this.repository);

  bool loading = false;
  String? error;
  List<Vehicle> vehicles = [];

  Future<void> load() async {
    loading = true;
    error = null;
    notifyListeners();
    final result = await repository.fetchVehicles();
    loading = false;
    if (result.isSuccess) {
      vehicles = result.data ?? [];
    } else {
      error = result.error;
    }
    notifyListeners();
  }
}
