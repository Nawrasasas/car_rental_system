import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../domain/rentals_repository.dart';

class CreateRentalPage extends StatefulWidget {
  const CreateRentalPage({super.key});

  @override
  State<CreateRentalPage> createState() => _CreateRentalPageState();
}

class _CreateRentalPageState extends State<CreateRentalPage> {
  final _form = GlobalKey<FormState>();
  final _customerId = TextEditingController();
  final _vehicleId = TextEditingController();
  final _branchId = TextEditingController();
  final _startDate = TextEditingController();
  final _endDate = TextEditingController();
  final _dailyRate = TextEditingController();

  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _customerId.dispose();
    _vehicleId.dispose();
    _branchId.dispose();
    _startDate.dispose();
    _endDate.dispose();
    _dailyRate.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final repo = context.read<RentalsRepository>();

    return Scaffold(
      appBar: AppBar(title: const Text('Create Rental')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _form,
          child: ListView(
            children: [
              const Text('Use IDs from backend lists (temporary MVP mode).'),
              const SizedBox(height: 12),
              _field(_customerId, 'Customer ID'),
              _field(_vehicleId, 'Vehicle ID'),
              _field(_branchId, 'Branch ID'),

              // حاشية: نعتمد وقت بغداد المحلي كما هو في النظام، وليس UTC
              _field(_startDate, 'Start Date (Baghdad: 2026-03-28 10:00:00)'),
              _field(_endDate, 'End Date (Baghdad: 2026-03-29 10:00:00)'),

              _field(_dailyRate, 'Daily Rate'),
              const SizedBox(height: 16),
              if (_error != null)
                Text(_error!, style: const TextStyle(color: Colors.red)),
              FilledButton(
                onPressed: _loading
                    ? null
                    : () async {
                        if (!_form.currentState!.validate()) return;

                        setState(() {
                          _loading = true;
                          _error = null;
                        });

                        try {
                          final customerId = int.parse(_customerId.text.trim());
                          final vehicleId = int.parse(_vehicleId.text.trim());
                          final branchId = int.parse(_branchId.text.trim());

                          final result = await repo.createRental({
                            'customer_id': customerId,
                            'vehicle_id': vehicleId,
                            'branch_id': branchId,
                            'start_date': _startDate.text.trim(),
                            'end_date': _endDate.text.trim(),
                            'daily_rate': _dailyRate.text.trim(),
                          });

                          if (!mounted) return;

                          setState(() => _loading = false);

                          if (result.isSuccess) {
                            Navigator.pop(context);
                          } else {
                            setState(() => _error = result.error);
                          }
                        } catch (e) {
                          if (!mounted) return;
                          setState(() {
                            _loading = false;
                            _error = 'Customer ID, Vehicle ID, and Branch ID must be numeric database IDs only.';
                          });
                        }
                      },
                child: _loading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Create Rental'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _field(TextEditingController c, String label) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: TextFormField(
        controller: c,
        decoration: InputDecoration(labelText: label),
        validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
      ),
    );
  }
}