import '../../../core/utils/result.dart';
import 'vehicle.dart';

abstract class VehiclesRepository {
  Future<Result<List<Vehicle>>> fetchVehicles();
  Future<Result<Vehicle>> fetchVehicle(int id);
}
