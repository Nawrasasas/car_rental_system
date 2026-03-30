import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app/app.dart';
import 'core/network/api_client.dart';
import 'core/storage/token_storage.dart';
import 'features/auth/data/auth_repository_impl.dart';
import 'features/auth/presentation/auth_controller.dart';
import 'features/rentals/data/rentals_repository_impl.dart';
import 'features/rentals/domain/rentals_repository.dart';
import 'features/rentals/presentation/rentals_controller.dart';
import 'features/vehicles/data/vehicles_repository_impl.dart';
import 'features/vehicles/domain/vehicles_repository.dart';
import 'features/vehicles/presentation/vehicles_controller.dart';

void main() {
  final apiClient = ApiClient(baseUrl: 'http://127.0.0.1:8000');
  final tokenStorage = TokenStorage();
  final vehiclesRepo = VehiclesRepositoryImpl(apiClient);
  final rentalsRepo = RentalsRepositoryImpl(apiClient);

  runApp(
    MultiProvider(
      providers: [
        Provider<ApiClient>.value(value: apiClient),
        Provider<VehiclesRepository>.value(value: vehiclesRepo),
        Provider<RentalsRepository>.value(value: rentalsRepo),
        ChangeNotifierProvider(
          create: (_) => AuthController(
            repository: AuthRepositoryImpl(apiClient, tokenStorage),
          )..restoreSession(),
        ),
        ChangeNotifierProvider(create: (_) => VehiclesController(vehiclesRepo)),
        ChangeNotifierProvider(create: (_) => RentalsController(rentalsRepo)),
      ],
      child: const CarRentalApp(),
    ),
  );
}
