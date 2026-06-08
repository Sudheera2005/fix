import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'dart:async';
import 'dart:convert';
import 'package:cc_group/shipment_assignment_view.dart';
import 'package:cc_group/login_page.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:cc_group/delivery_search_screen.dart';
import 'package:cc_group/qr_scanner_view.dart';

class HomePage extends StatefulWidget {
  final int userId;
  const HomePage({super.key, required this.userId});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  bool _isTracking = false;
  Position? _currentPosition;
  Timer? _timer;
  Map<String, dynamic>? _activeTask;
  bool _isLoadingTask = false;
  String? _accessToken;
  String? _username;
  List<dynamic> _notifications = [];
  bool _hasUnread = false;
  
  final String _baseApiUrl = "https://UnderpaidWorker.pythonanywhere.com/api/";

  Map<String, String> get _authHeaders => {
    'Content-Type': 'application/json',
    if (_accessToken != null) 'Authorization': 'Bearer $_accessToken',
  };

  @override
  void initState() {
    super.initState();
    _loadToken();
    _checkPermissions();
  }

  Future<void> _loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _accessToken = prefs.getString('access_token');
      _username = prefs.getString('username') ?? 'User';
    });
    _fetchActiveTask();
    _fetchNotifications();
  }

  void _showVehicleInfo() {
    final vehicle = _activeTask?['vehicle_details'];
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => Container(
        padding: const EdgeInsets.all(32),
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(40)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text("LOGISTICS ASSET", style: TextStyle(fontSize: 12, fontWeight: FontWeight.w900, color: Color(0xFFBCAAA4), letterSpacing: 2)),
                IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
              ],
            ),
            const SizedBox(height: 20),
            if (vehicle is Map) ...[
               Text(vehicle['plate_number'] ?? "N/A", style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w900, color: Color(0xFF3E2723))),
               const SizedBox(height: 8),
               Text(vehicle['vehicle_type'] ?? "Standard Unit", style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF8D6E63))),
               const SizedBox(height: 24),
               _buildVehicleDetail(Icons.monitor_weight_outlined, "Capacity", "${vehicle['capacity']} KG"),
               _buildVehicleDetail(Icons.ac_unit, "Refrigerated", vehicle['is_refrigerated'] == true ? "Yes" : "No"),
            ] else
               const Text("No vehicle currently assigned to this mission.", style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Color(0xFFBCAAA4))),
          ],
        ),
      ),
    );
  }

  Widget _buildVehicleDetail(IconData icon, String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Icon(icon, size: 18, color: const Color(0xFFBCAAA4)),
          const SizedBox(width: 12),
          Text("$label: ", style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Color(0xFFBCAAA4))),
          Text(value, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Color(0xFF3E2723))),
        ],
      ),
    );
  }

  Future<void> _fetchActiveTask() async {
    setState(() => _isLoadingTask = true);
    try {
      final response = await http.get(
        Uri.parse("${_baseApiUrl}shipments/driver_active/?user_id=${widget.userId}"),
        headers: _authHeaders,
      );
      
      if (response.statusCode == 200) {
        final Map<String, dynamic> shipment = jsonDecode(response.body);
        setState(() => _activeTask = shipment);
      } else {
        setState(() => _activeTask = null);
      }
    } catch (e) {
      debugPrint("Failed to load tasks: $e");
    } finally {
      setState(() => _isLoadingTask = false);
    }
  }

  Future<void> _fetchNotifications() async {
    try {
      final response = await http.get(
        Uri.parse("${_baseApiUrl}driver-notifications/?user_id=${widget.userId}"),
        headers: _authHeaders,
      );
      if (response.statusCode == 200) {
        final List<dynamic> notifs = jsonDecode(response.body);
        setState(() {
          _notifications = notifs;
          _hasUnread = notifs.isNotEmpty; // Simple unread logic
        });
      }
    } catch (e) {
      debugPrint("Failed to load notifications: $e");
    }
  }

  void _showNotificationInbox() {
    setState(() => _hasUnread = false);
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Container(
        height: MediaQuery.of(context).size.height * 0.6,
        padding: const EdgeInsets.all(32),
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(40)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text("NOTIFICATION INBOX", style: TextStyle(fontSize: 12, fontWeight: FontWeight.w900, color: Color(0xFFBCAAA4), letterSpacing: 2)),
                IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
              ],
            ),
            const SizedBox(height: 20),
            if (_notifications.isEmpty)
               const Expanded(child: Center(child: Text("No new notifications.", style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Color(0xFFBCAAA4)))))
            else
               Expanded(
                 child: ListView.builder(
                   itemCount: _notifications.length,
                   itemBuilder: (ctx, i) {
                     final notif = _notifications[i];
                     return Container(
                       margin: const EdgeInsets.only(bottom: 12),
                       padding: const EdgeInsets.all(16),
                       decoration: BoxDecoration(
                         color: const Color(0xFFFCFBF9),
                         border: Border.all(color: const Color(0xFFEFEBE9)),
                         borderRadius: BorderRadius.circular(16),
                       ),
                       child: Row(
                         crossAxisAlignment: CrossAxisAlignment.start,
                         children: [
                           const Icon(Icons.notifications_active, color: Color(0xFF3E2723), size: 20),
                           const SizedBox(width: 16),
                           Expanded(
                             child: Column(
                               crossAxisAlignment: CrossAxisAlignment.start,
                               children: [
                                 Text(notif['details'] ?? "Notification", style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Color(0xFF3E2723))),
                                 const SizedBox(height: 4),
                                 Text(notif['action'] ?? "", style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Color(0xFFBCAAA4))),
                               ],
                             ),
                           )
                         ],
                       )
                     );
                   },
                 ),
               )
          ],
        ),
      ),
    );
  }

  Future<void> _checkPermissions() async {
    bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) return;

    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
  }

  Future<void> _startTracking() async {
    bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Location services are disabled.")));
      return;
    }

    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) return;
    }
    
    if (permission == LocationPermission.deniedForever) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Location permissions are permanently denied. Please enable them in settings.")));
      await Geolocator.openAppSettings();
      return;
    }

    setState(() => _isTracking = true);

    _timer = Timer.periodic(const Duration(seconds: 10), (timer) async {
      try {
        Position position = await Geolocator.getCurrentPosition(desiredAccuracy: LocationAccuracy.high);
        setState(() => _currentPosition = position);
        _sendLocationToBackend(position);
      } catch (e) {
        debugPrint("Location error: $e");
        // Don't crash the timer, just let it retry next tick
      }
    });
  }

  void _stopTracking() {
    setState(() => _isTracking = false);
    _timer?.cancel();
  }

  Future<void> _sendLocationToBackend(Position position) async {
    try {
      await http.post(
        Uri.parse("${_baseApiUrl}tracking/location/"),
        headers: _authHeaders,
        body: jsonEncode(<String, dynamic>{
          'driver_id': widget.userId.toString(),
          'latitude': position.latitude,
          'longitude': position.longitude,
          'timestamp': DateTime.now().toIso8601String(),
          'status': 'active',
        }),
      );
    } catch (e) {}
  }

  Future<void> _logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('access_token');
    await prefs.remove('username');
    if (mounted) {
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (context) => const LoginPage()),
        (route) => false,
      );
    }
  }

  void _handleVehicleAction(bool isReturn) async {
    final vehicle = _activeTask?['vehicle_details'];
    final vId = vehicle?['id'];
    
    if (vId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("No vehicle associated with this mission."))
      );
      return;
    }

    final messenger = ScaffoldMessenger.of(context);
    final authHeaders = Map<String, String>.from(_authHeaders);
    final baseUrl = _baseApiUrl;
    final homeContext = context;

    bool? confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Checkout Vehicle"),
        content: Text("Do you confirm you are taking possession of vehicle ${vehicle?['plate_number']}?"),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("CANCEL")),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text("CONFIRM CHECKOUT")),
        ],
      ),
    );

    if (confirm != true) return;

    try {
      final res = await http.post(
        Uri.parse("${baseUrl}vehicles/$vId/checkout_vehicle/"),
        headers: authHeaders,
      );
      if (res.statusCode == 200) {
        messenger.showSnackBar(const SnackBar(content: Text("Vehicle checked out. You are ready for dispatch.")));
        _fetchActiveTask();
      } else {
        String err;
        try {
          err = jsonDecode(res.body)['error'] ?? "Response: ${res.body}";
        } catch(e) {
          err = "Status ${res.statusCode}: ${res.body}";
        }
        showDialog(
          context: homeContext, 
          builder: (c) => AlertDialog(
            title: const Text("Checkout Failed"), 
            content: Text(err), 
            actions: [TextButton(onPressed: () => Navigator.pop(c), child: const Text("OK"))]
          )
        );
      }
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text("Network error: $e")));
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFCFBF9), // Cream canvas
      body: SafeArea(
        child: Column(
          children: [
            // 1. Transmission Status Banner (Amber Warning)
            if (!_isTracking)
              GestureDetector(
                onTap: _startTracking,
                child: Container(
                  width: double.infinity,
                  color: const Color(0xFFFFB300), // Amber
                  padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 20),
                  child: const Row(
                    children: [
                      Icon(Icons.warning_amber_rounded, color: Colors.black, size: 20),
                      SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          "TRANSMISSION PAUSED: LOGS DEACTIVATED",
                          style: TextStyle(fontWeight: FontWeight.w900, fontSize: 11, color: Colors.black, letterSpacing: 0.5),
                        ),
                      ),
                      Text("RESUME", style: TextStyle(fontWeight: FontWeight.w900, fontSize: 11, color: Colors.black, decoration: TextDecoration.underline)),
                    ],
                  ),
                ),
              ),

            Expanded(
              child: SingleChildScrollView(
                physics: const BouncingScrollPhysics(),
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // 2. Driver Profile Header (Minimalist Greeting)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        GestureDetector(
                          onTap: _showVehicleInfo,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                "HELLO, ${_username?.toUpperCase() ?? 'USER'}",
                                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: Color(0xFF3E2723), letterSpacing: -0.5),
                              ),
                              const SizedBox(height: 4),
                              Row(
                                children: [
                                  Container(
                                    width: 8,
                                    height: 8,
                                    decoration: BoxDecoration(
                                      color: _isTracking ? Colors.green : Colors.red,
                                      shape: BoxShape.circle,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Text(
                                    _isTracking ? "ONLINE / ACTIVE" : "OFFLINE / STANDBY",
                                    style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: Color(0xFFBCAAA4), letterSpacing: 1),
                                  ),
                                ],
                              ),
                              if (_activeTask?['is_checked_out'] == true) ...[
                                const SizedBox(height: 8),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                  decoration: BoxDecoration(
                                    color: Colors.green.withOpacity(0.1),
                                    borderRadius: BorderRadius.circular(4),
                                    border: Border.all(color: Colors.green.withOpacity(0.2)),
                                  ),
                                  child: const Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(Icons.check_circle, size: 10, color: Colors.green),
                                      SizedBox(width: 4),
                                      Text(
                                        "READY FOR DISPATCH / ASSET IN POSSESSION",
                                        style: TextStyle(fontSize: 8, fontWeight: FontWeight.w900, color: Colors.green, letterSpacing: 0.5),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                        Row(
                          children: [
                            Stack(
                              children: [
                                IconButton(
                                  onPressed: _showNotificationInbox,
                                  icon: const Icon(Icons.notifications_none, color: Color(0xFF3E2723)),
                                ),
                                if (_hasUnread)
                                  Positioned(
                                    right: 10,
                                    top: 10,
                                    child: Container(
                                      width: 8,
                                      height: 8,
                                      decoration: const BoxDecoration(color: Colors.red, shape: BoxShape.circle),
                                    ),
                                  )
                              ],
                            ),
                            IconButton(
                              onPressed: _logout,
                              icon: const Icon(Icons.logout, color: Color(0xFF3E2723)),
                            )
                          ],
                        )
                      ],
                    ),

                    const SizedBox(height: 40),

                    // 3. Main Action Context (What's next?)
                    Text(
                      "ACTIVE MISSION",
                      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w900, color: const Color(0xFF3E2723).withOpacity(0.3), letterSpacing: 2),
                    ),
                    const SizedBox(height: 16),

                    if (_isLoadingTask)
                      const Center(child: Padding(padding: EdgeInsets.all(40), child: CircularProgressIndicator(color: Color(0xFF3E2723))))
                    else if (_activeTask != null)
                      _buildMissionCard()
                    else
                      _buildIdleState(),

                    const SizedBox(height: 32),
                    // Fleet Action Panel - DYNAMIC BUTTONS
                    const SizedBox(height: 16),
                    if (_activeTask != null && _activeTask?['is_checked_out'] == false)
                      GestureDetector(
                        onTap: () => _handleVehicleAction(false),
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.symmetric(vertical: 20),
                          decoration: BoxDecoration(
                            color: const Color(0xFF3E2723),
                            borderRadius: BorderRadius.circular(20),
                            boxShadow: [
                              BoxShadow(color: const Color(0xFF3E2723).withOpacity(0.1), blurRadius: 10, offset: const Offset(0, 5)),
                            ],
                          ),
                          child: const Column(
                            children: [
                              Icon(Icons.login_rounded, color: Colors.white),
                              SizedBox(height: 8),
                              Text("CHECKOUT ASSET", style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: 1.5)),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),

            // 4. Primary Sticky Action Button (Global Context)
            _buildStickyActionButton(),
          ],
        ),
      ),
    );
  }

  Widget _buildMissionCard() {
    final status = _activeTask!['status'] ?? 'planned';
    final isOutbound = _activeTask!['assignment_type'] != 'inbound';
    final manifestId = isOutbound ? "MF-${_activeTask!['shipment_id']}" : "CL-${_activeTask!['id'].toString().substring(0,6)}";

    return GestureDetector(
      onTap: () {
        if (!isOutbound) {
            Navigator.pushNamed(context, '/inbound/assignment', arguments: _activeTask);
        } else {
            Navigator.push(context, MaterialPageRoute(builder: (c) => ShipmentAssignmentView(userId: widget.userId, baseUrl: _baseApiUrl)));
        }
      },
      child: Container(
        padding: const EdgeInsets.all(32),
        width: double.infinity,
        decoration: BoxDecoration(
          color: const Color(0xFF3E2723), // Dark Brown
          borderRadius: BorderRadius.circular(40),
          boxShadow: [
            BoxShadow(color: const Color(0xFF3E2723).withOpacity(0.2), blurRadius: 30, offset: const Offset(0, 15)),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  manifestId,
                  style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: -1),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(color: Colors.white.withOpacity(0.1), borderRadius: BorderRadius.circular(10)),
                  child: Text(
                    status.toUpperCase(),
                    style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: 1),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            Text(
              "NEXT STOP",
              style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: Colors.white.withOpacity(0.4), letterSpacing: 2),
            ),
            const SizedBox(height: 8),
            Text(
              isOutbound ? "Main Distribution Center" : (_activeTask!['supplier']?['name'] ?? "Warehouse"),
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: -0.5),
            ),
            const SizedBox(height: 32),
            
            // Minimal Step Tracker
            Row(
              children: [
                _buildStepDot(true),
                _buildStepLine(status != 'planned' && status != 'dispatched'),
                _buildStepDot(status != 'planned' && status != 'dispatched'),
                _buildStepLine(status == 'in_transit'),
                _buildStepDot(status == 'in_transit'),
                _buildStepLine(false),
                _buildStepDot(false),
              ],
            )
          ],
        ),
      ),
    );
  }

  Widget _buildStepDot(bool active) {
    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        color: active ? const Color(0xFFBCAAA4) : Colors.white.withOpacity(0.1),
        shape: BoxShape.circle,
      ),
    );
  }

  Widget _buildStepLine(bool active) {
    return Expanded(
      child: Container(
        height: 2,
        color: active ? const Color(0xFFBCAAA4) : Colors.white.withOpacity(0.1),
      ),
    );
  }

  Widget _buildIdleState() {
    return Container(
      padding: const EdgeInsets.all(40),
      width: double.infinity,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(40),
        border: Border.all(color: const Color(0xFFEFEBE9)),
      ),
      child: Column(
        children: [
          Icon(Icons.assignment_turned_in_outlined, size: 48, color: const Color(0xFFD7CCC8)),
          const SizedBox(height: 16),
          const Text(
            "NO ASSIGNED MISSIONS",
            style: TextStyle(fontWeight: FontWeight.w900, fontSize: 13, color: Color(0xFFBCAAA4), letterSpacing: 1),
          ),
          const SizedBox(height: 8),
          const Text(
            "Stand by for terminal instructions.",
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Color(0xFFD7CCC8)),
          ),
        ],
      ),
    );
  }

  Widget _buildStickyActionButton() {
    String label = "START TRACKING";
    Color btnColor = const Color(0xFF3E2723);
    IconData icon = Icons.play_arrow_rounded;
    VoidCallback action = _startTracking;

    if (_isTracking) {
      if (_activeTask == null) {
        label = "RELOAD MISSIONS";
        icon = Icons.refresh_rounded;
        action = _fetchActiveTask;
      } else {
        final status = _activeTask!['status'];
        if (status == 'dispatched' || status == 'planned') {
          label = "OPEN ASSIGNMENT";
          icon = Icons.assignment_rounded;
        } else if (status == 'accepted') {
          label = "START NAVIGATION";
          icon = Icons.navigation_rounded;
        } else {
          label = "VIEW MISSION DETAILS";
          icon = Icons.explore_rounded;
        }
        action = () {
             if (_activeTask!['assignment_type'] == 'inbound') {
                Navigator.pushNamed(context, '/inbound/assignment', arguments: _activeTask);
             } else {
                Navigator.push(context, MaterialPageRoute(builder: (c) => ShipmentAssignmentView(userId: widget.userId, baseUrl: _baseApiUrl)));
             }
        };
      }
    }

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: const Color(0xFFEFEBE9))),
      ),
      child: ElevatedButton(
        onPressed: action,
        style: ElevatedButton.styleFrom(
          backgroundColor: btnColor,
          minimumSize: const Size(double.infinity, 72),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          elevation: 0,
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: Colors.white, size: 28),
            const SizedBox(width: 12),
            Text(
              label,
              style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w900, letterSpacing: 1),
            ),
          ],
        ),
      ),
    );
  }
}
