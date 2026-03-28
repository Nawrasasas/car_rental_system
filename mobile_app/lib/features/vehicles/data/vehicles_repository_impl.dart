import '../../../core/constants/api_endpoints.dart';
import '../../../core/network/api_client.dart';
import '../../../core/utils/result.dart';
import '../domain/vehicle.dart';
import '../domain/vehicles_repository.dart';

class VehiclesRepositoryImpl implements VehiclesRepository {
  final ApiClient _api;
  VehiclesRepositoryImpl(this._api);

  @override
  Future<Result<List<Vehicle>>> fetchVehicles() async {
    try {
      final response = await _api.get(ApiEndpoints.vehicles);
      final raw = (response['results'] ?? response['data'] ?? []) as List<dynamic>;
      return Result.success(raw.map((e) => Vehicle.fromJson(e as Map<String, dynamic>)).toList());
    } catch (e) {
      return Result.failure(e.toString().replaceFirst('Exception: ', ''));
    }
  }

  @override
  Future<Result<Vehicle>> fetchVehicle(int id) async {
    try {
      final response = await _api.get('${ApiEndpoints.vehicles}$id/');
      return Result.success(Vehicle.fromJson(response));
    } catch (e) {
      return Result.failure(e.toString().replaceFirst('Exception: ', ''));
    }
  }
}
