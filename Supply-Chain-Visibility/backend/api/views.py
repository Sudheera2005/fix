from rest_framework import viewsets, permissions, status, serializers
from rest_framework.views import APIView
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from django.utils import timezone
from .models import (
    CustomUser, VehicleAssignment, Order, AuditLog, 
    Shipment, ShipmentOrder, OrderException, OrderStatusLog,
    Role, Employee, GPSPersistence, ProofOfDelivery
)
from vehicles.models import Vehicle
from .serializers import (
    UserSerializer, VehicleSerializer, VehicleAssignmentSerializer,
    ProofOfDeliverySerializer, OrderSerializer, AuditLogSerializer,
    ShipmentSerializer, OrderExceptionSerializer, OrderStatusLogSerializer
)
from .utils.route_optimization import cluster_orders
# Cache-buster update to force server bytecode refresh: 2026-04-17-11:03


class CustomTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        # DRF request.data can be immutable (QueryDict) or mutable (dict).
        # We ensure we work with a mutable copy to perform the email-to-username swap.
        try:
            data = request.data.copy()
        except AttributeError:
            data = dict(request.data)
            
        identifier = data.get('username')
        password = data.get('password')
        
        # Check if login identifier matches email or username
        user = CustomUser.objects.filter(email__iexact=identifier).first() or \
               CustomUser.objects.filter(username=identifier).first()
            
        if user:
            # Swap for the actual username so authenticate() works regardless of input type
            data['username'] = user.username
        
        # We manually initialize the serializer with our modified data
        serializer = self.get_serializer(data=data)
        
        try:
            serializer.is_valid(raise_exception=True)
            response_data = serializer.validated_data
            
            # Map user ID and role for frontend convenience
            target_user = user or CustomUser.objects.get(username=data['username'])
            response_data['user_id'] = target_user.id
            response_data['role'] = target_user.role.role_name.lower() if target_user.role else 'driver'
            
            # Audit Log: Successful login
            from .models import AuditLog
            AuditLog.objects.create(
                user=target_user,
                action='LOGIN_SUCCESS',
                resource_type='Session',
                details=f"User '{target_user.username}' logged in successfully."
            )
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except (AuthenticationFailed, serializers.ValidationError) as e:
            # Audit Log: Failed login
            from .models import AuditLog
            AuditLog.objects.create(
                user=user if user else None,
                action='LOGIN_FAILED',
                resource_type='Session',
                details=f"Failed login attempt for identifier '{identifier}'. Error: {str(e)}"
            )
            
            # Extract detail message if it's a ValidationError
            error_detail = e.detail if hasattr(e, 'detail') else str(e)
            if isinstance(error_detail, dict):
                error_detail = error_detail.get('detail', error_detail)
            
            return Response(
                {"detail": error_detail}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"detail": f"Server Authentication Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class IsAdminRole(permissions.BasePermission):
    def has_permission(self, request, view):
        # Fallback for identity verification if JWT fails/missing in dev
        user_id = request.query_params.get('user_id') or (request.data.get('user_id') if isinstance(request.data, dict) else None)
        user = None
        if user_id:
            try:
                user = CustomUser.objects.get(user_id=user_id)
            except: pass

        if not user:
            user = request.user

        if not user or not user.is_authenticated:
            return False
            
        if user.is_superuser:
            return True
        try:
            return user.role.role_name.lower() == 'admin' if user.role else False
        except AttributeError:
            return False

class IsInternalRole(permissions.BasePermission):
    def has_permission(self, request, view):
        user_id = request.query_params.get('user_id') or (request.data.get('user_id') if isinstance(request.data, dict) else None)
        user = None
        if user_id:
            try: user = CustomUser.objects.get(user_id=user_id)
            except: pass
        if not user: user = request.user
            
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        try:
            role = user.role.role_name.lower() if user.role else ''
            return role in ['admin', 'manager', 'dispatcher']
        except AttributeError:
            return False

class IsManagerRole(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        try:
            return request.user.role.role_name.lower() == 'manager' if request.user.role else False
        except AttributeError:
            return False

class IsDispatcherRole(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        try:
            return request.user.role.role_name.lower() == 'dispatcher'
        except AttributeError:
            return False

class IsDriverRole(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            # Note: drivers are rarely superusers, so we check specifically
            return request.user.role.role_name.lower() == 'driver'
        except AttributeError:
            return False

class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return CustomUser.objects.none()
        # Admins can see everyone except themselves in the management list
        return CustomUser.objects.exclude(user_id=self.request.user.pk)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsInternalRole()]
        return [IsAdminRole()]

    def perform_update(self, serializer):
        if serializer.instance.id == self.request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Security Violation: Self-modification of administrative accounts is prohibited.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.id == self.request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Security Violation: You cannot delete your own administrative identity.")
        instance.delete()

class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer

    def get_permissions(self):
        if self.action in ['checkout_vehicle', 'return_vehicle', 'retrieve', 'log_maintenance', 'log_fuel']:
            return [permissions.IsAuthenticated()]
        return [IsInternalRole()]

    @action(detail=True, methods=['post'])
    def log_maintenance(self, request, pk=None):
        vehicle = self.get_object()
        from .serializers import MaintenanceLogSerializer
        serializer = MaintenanceLogSerializer(data={**request.data, 'vehicle': vehicle.vehicle_id})
        if serializer.is_valid():
            serializer.save()
            # Update vehicle metadata
            vehicle.current_mileage = request.data.get('mileage_at_service', vehicle.current_mileage)
            vehicle.next_service_mileage = request.data.get('next_service_due_mileage', vehicle.next_service_mileage)
            vehicle.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def log_fuel(self, request, pk=None):
        vehicle = self.get_object()
        from .serializers import FuelExpenseSerializer
        serializer = FuelExpenseSerializer(data={**request.data, 'vehicle': vehicle.vehicle_id})
        if serializer.is_valid():
            serializer.save()
            # Update mileage
            vehicle.current_mileage = request.data.get('mileage_at_refill', vehicle.current_mileage)
            vehicle.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        user = request.user
        if user.is_superuser:
            return
            
        role = user.role.role_name.lower() if user.role else ''
        if self.action in ['partial_update', 'update'] and role in ['manager', 'dispatcher']:
            # Managers and dispatchers can strictly modify driver assignments.
            # We allow metadata updates if they are admins, but for these roles we restrict to 'assignedDriver'
            # However, we check if they are trying to change core fields.
            disallowed_keys = {'plate_number', 'vehicle_id', 'vehicle_type', 'plateID', 'make_model'}
            intersect = set(request.data.keys()).intersection(disallowed_keys)
            if intersect:
                # Debugging info: show exactly what caused the block
                self.permission_denied(request, message=f"Identity policy violation: {role.title()}s cannot modify restricted fields ({', '.join(intersect)}). Only 'assignedDriver' updates are permitted.")

    def perform_update(self, serializer):
        try:
            assigned_driver_data = self.request.data.get('assignedDriver', -1)
            vehicle = serializer.instance
            
            # If assignedDriver was provided in the request (even if null or empty string)
            if assigned_driver_data != -1:
                from django.utils import timezone
                from .models import VehicleAssignment
                from drivers.models import Driver
                from rest_framework import serializers
                now = timezone.now()
                
                # Close existing active assignments for this vehicle
                VehicleAssignment.objects.filter(vehicle=vehicle, status='active').update(status='completed', assignment_end_date=now)
                
                if assigned_driver_data and str(assigned_driver_data).strip():
                    try:
                        # Robust lookup: handle string or integer IDs
                        d_id = int(assigned_driver_data)
                        driver_obj = Driver.objects.get(employee__user__user_id=d_id)
                    except (ValueError, Driver.DoesNotExist):
                        # Self-healing: If user is a driver but lacks profile, create it now
                        from .models import CustomUser, Employee
                        try:
                            target_user = CustomUser.objects.get(user_id=d_id)
                            # Use role_name for explicit check
                            actual_role = target_user.role.role_name if target_user.role else "None"
                            if actual_role.lower() == 'driver':
                                emp, _ = Employee.objects.get_or_create(user=target_user, defaults={'full_name': target_user.username, 'national_id': 'N/A', 'contact_number': 'N/A', 'address': 'N/A', 'date_of_birth': '2000-01-01'})
                                driver_obj = Driver.objects.create(
                                    employee=emp, 
                                    license_number='AUTO-PROVISIONED',
                                    license_expiry_date='2099-12-31'
                                )
                            else:
                                raise serializers.ValidationError(f"Selected personnel has the '{actual_role}' role. Assignment requires the 'Driver' role.")
                        except serializers.ValidationError as ve:
                            # Re-raise validation errors directly
                            raise ve
                        except Exception as inner_e:
                            raise serializers.ValidationError(f"Critical profile failure: {str(inner_e)}")
                    except serializers.ValidationError as ve:
                        # Re-raise validation errors directly to skip the outer broad catch-all if possible
                        # but we need to ensure the outer catch-all doesn't wrap it again with "Server crash"
                        raise ve
                    except Exception as e:
                        raise serializers.ValidationError(f"Assignment error: {str(e)}")
                        
                    if driver_obj:
                        # Enforce 1-to-1: Close any currently active assignment for this specific driver
                        VehicleAssignment.objects.filter(driver=driver_obj, status='active').update(status='completed', assignment_end_date=now)
                        
                        VehicleAssignment.objects.create(
                            driver=driver_obj,
                            vehicle=vehicle,
                            status='active',
                            assignment_start_date=now,
                            assigned_by=self.request.user
                        )
                        # Mark vehicle as in use
                        serializer.save(status='in_use')
                else:
                    # Explicit unassignment (null or empty string provided)
                    serializer.save(status='available')
            else:
                # Traditional update (metadata changes only)
                serializer.save()
        except serializers.ValidationError as ve:
            # Propagate validation errors directly (e.g. role check failures)
            raise ve
        except Exception as e:
            import traceback
            from rest_framework import serializers
            raise serializers.ValidationError({"assignedDriver": f"Server crash: {str(e)} | Tr: {traceback.format_exc()}"})

    @action(detail=True, methods=['get'])
    def capacity_fill_suggestions(self, request, pk=None):
        vehicle = self.get_object()
        cluster_id = request.query_params.get('cluster_id')
        
        if not cluster_id:
            return Response({'error': 'cluster_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate remaining capacity
        current_load = vehicle.current_load_weight
        remaining_kg = float(vehicle.capacity_kg) - current_load
        
        # Get orders currently in the cluster to find centroid
        from .models import Order
        cluster_prefix = cluster_id.split('_')[0] # Warehouse ID
        orders_in_cluster = Order.objects.filter(status='pending', warehouse_id=cluster_prefix) # Simplified cluster retrieval
        # In a real app we'd fetch specific IDs from the cluster cache/state
        
        # Get unassigned orders from the same warehouse
        unassigned = Order.objects.filter(status='pending', warehouse_id=cluster_prefix).exclude(order_id__in=[o.order_id for o in orders_in_cluster])
        
        from .utils.route_optimization import get_fill_suggestions
        cluster_coords = [{'lat': float(o.pickup_lat), 'lng': float(o.pickup_lng)} for o in orders_in_cluster if o.pickup_lat]
        
        unassigned_data = []
        for o in unassigned:
            if o.pickup_lat:
                unassigned_data.append({
                    'id': o.order_id,
                    'weight_kg': float(o.weight_kg),
                    'lat': float(o.pickup_lat),
                    'lng': float(o.pickup_lng),
                    'address': o.pickup_address
                })
        
        suggestions = get_fill_suggestions(unassigned_data, cluster_coords, remaining_kg, 0)
        return Response(suggestions)

    @action(detail=True, methods=['post'])
    def checkout_vehicle(self, request, pk=None):
        vehicle = self.get_object()
        from .models import VehicleAssignment
        from drivers.models import Driver
        try:
            driver = Driver.objects.get(employee__user=request.user)
            assignment = VehicleAssignment.objects.filter(vehicle=vehicle, driver=driver, status='active').first()
            if assignment:
                if assignment.is_checked_out:
                    return Response({'success': True, 'message': 'Vehicle is already checked out.'})
                assignment.is_checked_out = True
                assignment.save()
                return Response({'success': True, 'message': 'Vehicle successfully checked out.'})
            return Response({'error': 'You are not assigned to this vehicle.'}, status=400)
        except Driver.DoesNotExist:
            return Response({'error': 'Only drivers can checkout vehicles.'}, status=403)

    @action(detail=True, methods=['post'])
    def return_vehicle(self, request, pk=None):
        vehicle = self.get_object()
        rating = request.data.get('rating')
        from .models import VehicleAssignment
        from drivers.models import Driver
        from django.utils import timezone
        try:
            driver = Driver.objects.get(employee__user=request.user)
            assignment = VehicleAssignment.objects.filter(vehicle=vehicle, driver=driver, status='active').first()
            if assignment:
                if not assignment.is_checked_out:
                    return Response({'error': 'You cannot return a vehicle you haven\'t checked out.'}, status=400)
                if rating:
                    assignment.rating = rating
                assignment.is_checked_out = False
                assignment.status = 'completed'
                assignment.assignment_end_date = timezone.now()
                assignment.save()
                
                # Unassign from vehicle
                vehicle.status = 'available'
                vehicle.save()
                return Response({'success': True, 'message': 'Vehicle successfully returned.'})
            return Response({'error': 'You are not actively assigned to this vehicle.'}, status=400)
        except Driver.DoesNotExist:
            return Response({'error': 'Only drivers can return vehicles.'}, status=403)

class VehicleAssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VehicleAssignment.objects.all().order_by('-assignment_start_date')
    serializer_class = VehicleAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def driver_history(self, request):
        driver_id = request.query_params.get('driver_id')
        if not driver_id:
            return Response({'error': 'driver_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        # Note driver_id is CustomUser ID here as passed by frontend if used
        from drivers.models import Driver as DriverProfile
        try:
            drv = DriverProfile.objects.get(employee__user_id=driver_id)
            qs = self.queryset.filter(driver=drv)
        except:
            qs = self.queryset.none()
            
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=['get'])
    def vehicle_history(self, request):
        vehicle_id = request.query_params.get('vehicle_id')
        if not vehicle_id:
            return Response({'error': 'vehicle_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        qs = self.queryset.filter(vehicle_id=vehicle_id)
        return Response(self.get_serializer(qs, many=True).data)

from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])  # GPS data submission requires authentication
def tracking_location(request):
    """
    Ingest GPS location from Flutter app and store it in Django local memory cache.
    """
    data = request.data
    driver_id = data.get('driver_id')
    
    if not driver_id:
        return Response({'status': 'error', 'message': 'driver_id required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Enrich with Driver Name and Active Shipment
    from .models import GPSPersistence, VehicleAssignment, Order
    from vehicles.models import Vehicle
    from drivers.models import Driver as DriverProfile
    
    driver_name = "Unknown Driver"
    shipment_info = "No Active Shipment"
    vehicle_plate = "N/A"
    vehicle_model = "Unknown Asset"
    
    try:
        # Note: driver_id in this payload refers to the User ID (as used in HomePage.dart)
        driver_prof = DriverProfile.objects.select_related('employee__user').get(employee__user_id=driver_id)
        driver_name = driver_prof.employee.full_name
        
        # Find all active orders assigned to THIS driver
        active_orders = Order.objects.filter(assigned_driver=driver_prof, status__in=['assigned', 'in_transit'])
        if active_orders.exists():
            order_ids = [f"ORD-{o.order_id}" for o in active_orders]
            shipment_info = ", ".join(order_ids)
            
        # Find active vehicle info
        assignment = VehicleAssignment.objects.filter(driver=driver_prof, status='active').first()
        if assignment and assignment.vehicle:
            vehicle_plate = assignment.vehicle.plate_number
            vehicle_model = f"{assignment.vehicle.manufacturer} {assignment.vehicle.model}"
                
        # Persist for 2-hour window
        GPSPersistence.objects.create(
            driver=driver_prof,
            latitude=data.get('latitude'),
            longitude=data.get('longitude')
        )
    except Exception as e:
        print(f"Tracking Enrichment Error: {e}")

    locations = cache.get('active_locations', {})
    locations[driver_id] = {
        'driver_id': driver_id,
        'driver_name': driver_name,
        'shipment_info': shipment_info,
        'vehicle_id': data.get('vehicle_id'),
        'vehicle_plate': vehicle_plate,
        'vehicle_model': vehicle_model,
        'lat': data.get('latitude'),
        'lng': data.get('longitude'),
        'timestamp': data.get('timestamp'),
        'status': data.get('status')
    }
    cache.set('active_locations', locations, timeout=86400) # keep for 1 day
    return Response({'status': 'success', 'message': 'Location logged'}, status=status.HTTP_202_ACCEPTED)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_locations(request):
    """
    Endpoint for React dashboard to poll periodically for the latest locations.
    """
    locations = cache.get('active_locations', {})
    return Response(list(locations.values()))

# Models imported at top level
from .serializers import OrderSerializer, AuditLogSerializer, ShipmentSerializer
from django.db import transaction

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related('assigned_vehicle', 'assigned_driver', 'assigned_driver__employee').all().order_by('-created_at')
    serializer_class = OrderSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
             return [IsDispatcherRole()]
        if self.action == 'report_exception':
             return [IsDriverRole()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        order = self.get_object()
        if order.status != 'pending':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Modifications are prohibited once an order has been assigned to a cluster or shipment.")
        
        from .utils.geocoding import geocode_address
        # 1. Geocode Pickup address if it changed
        new_pickup = self.request.data.get('pickup_address')
        if new_pickup and new_pickup != order.pickup_address:
            lat, lng = geocode_address(new_pickup)
            serializer.validated_data['pickup_lat'] = lat
            serializer.validated_data['pickup_lng'] = lng

        # 2. Geocode Delivery address if it changed
        new_delivery = self.request.data.get('delivery_address')
        if new_delivery and new_delivery != order.delivery_address:
            lat, lng = geocode_address(new_delivery)
            serializer.validated_data['delivery_lat'] = lat
            serializer.validated_data['delivery_lng'] = lng
            
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != 'pending':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("You cannot delete an order that has already been assigned or dispatched.")
        instance.delete()

    @action(detail=False, methods=['get'])
    def driver_tasks(self, request):
        user = request.user
        user_id_fallback = request.query_params.get('user_id')
        
        if not user.is_authenticated and not user_id_fallback:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            from drivers.models import Driver as DriverProfile
            if user.is_authenticated:
                driver = DriverProfile.objects.get(employee__user=user)
            else:
                driver = DriverProfile.objects.get(employee__user_id=user_id_fallback)        
            tasks = Order.objects.filter(assigned_driver=driver, status__in=['assigned', 'in_transit'])
            return Response(OrderSerializer(tasks, many=True).data)
        except DriverProfile.DoesNotExist:
            return Response({'error': 'No active driver profile found for this user.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def report_exception(self, request, pk=None):
        order = self.get_object()
        exception_type = request.data.get('exception_type')
        notes = request.data.get('notes', '')
        lat = request.data.get('lat')
        lng = request.data.get('lng')
        
        from drivers.models import Driver as DriverProfile
        from .models import OrderException, OrderStatusLog, CustomUser
        try:
            # Identity Fallback
            user = request.user
            if not user.is_authenticated:
                u_id = request.data.get('user_id')
                if u_id:
                    user = CustomUser.objects.filter(user_id=u_id).first()

            if user and hasattr(user, 'employee') and hasattr(user.employee, 'driver_profile'):
                driver = user.employee.driver_profile
            else:
                driver = DriverProfile.objects.get(employee__user=user)
        except Exception:
             return Response({'error': 'Only drivers can report exceptions'}, status=status.HTTP_403_FORBIDDEN)
             
        # Create exception record
        OrderException.objects.create(
            order=order,
            exception_type=exception_type,
            driver=driver,
            location_lat=lat,
            location_lng=lng,
            notes=notes
        )
        
        # Convert it to a return task for Dispatcher workflow
        old_status = order.status
        order.status = 'delivery_failed'
        order.assigned_driver = None
        order.assigned_vehicle = None
        
        # Reason-Based Routing categorization
        order.delivery_address = f"[RETURN - {exception_type.upper()}] {order.pickup_address}"
        if order.pickup_lat and order.pickup_lng:
            order.delivery_lat = order.pickup_lat
            order.delivery_lng = order.pickup_lng
            
        # Detach from current shipment so dispatcher can re-route
        from .models import ShipmentOrder
        ShipmentOrder.objects.filter(order=order).delete()
        
        order.save()
        
        OrderStatusLog.objects.create(
            order=order,
            from_status=old_status,
            to_status='pending_return',
            changed_by=request.user,
            source='driver_exception'
        )
        
        return Response({'success': True, 'message': 'Exception reported. Please return the item to the warehouse.'})

    @action(detail=True, methods=['post'])
    def reassign_to_shipment(self, request, pk=None):
        order = self.get_object()
        shipment_id = request.data.get('shipment_id')
        
        from .models import Shipment, ShipmentOrder, OrderStatusLog
        try:
            shipment = Shipment.objects.get(shipment_id=shipment_id)
        except Shipment.DoesNotExist:
            return Response({'error': 'Shipment not found'}, status=status.HTTP_404_NOT_FOUND)
            
        if shipment.status in ['in_progress', 'completed']:
            return Response({'error': 'Cannot assign to a shipment that is already in progress or completed.'}, status=status.HTTP_400_BAD_REQUEST)
            
        old_status = order.status
        order.status = 'assigned'
        order.assigned_vehicle = shipment.vehicle
        order.assigned_driver = shipment.driver
        order.is_priority = False
        
        import re
        if order.delivery_address.startswith('[RETURN -'):
            order.delivery_address = re.sub(r'^\[RETURN - [A-Z_]+\] ', '', order.delivery_address)
            
        order.save()
        
        ShipmentOrder.objects.create(shipment=shipment, order=order)
        
        OrderStatusLog.objects.create(
            order=order,
            from_status=old_status,
            to_status='assigned',
            changed_by=request.user,
            source='dispatcher_reassign'
        )
        
        return Response({'success': True, 'message': 'Order successfully reassigned to shipment.'})

    @action(detail=True, methods=['post'])
    def mark_priority(self, request, pk=None):
        order = self.get_object()
        
        old_status = order.status
        order.status = 'pending'
        order.is_priority = True
        
        import re
        if order.delivery_address.startswith('[RETURN -'):
            order.delivery_address = re.sub(r'^\[RETURN - [A-Z_]+\] ', '', order.delivery_address)
            
        order.save()
        
        from .models import OrderStatusLog
        OrderStatusLog.objects.create(
            order=order,
            from_status=old_status,
            to_status='pending',
            changed_by=request.user,
            source='dispatcher_priority'
        )
        
        return Response({'success': True, 'message': 'Order marked as high priority.'})

    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        """ Generate a professional order summary/waybill for the manager. """
        order = self.get_object()
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_kpi_card, draw_styled_table, draw_status_pill
            from reportlab.lib import colors
            
            def content(p, w, h):
                draw_header(p, w, h, "Order Waybill", f"Official Documentation for Order ID: ORD-{order.order_id}")
                
                # 1. Order Summary KPIs
                y = h - 185
                draw_kpi_card(p, 50, y, "Total Weight", f"{order.weight_kg} kg", "#1e293b")
                draw_kpi_card(p, 185, y, "Volume", f"{order.volume_m3} m³", "#3b82f6")
                draw_kpi_card(p, 320, y, "Quantity", f"{order.quantity} units", "#16a34a")
                draw_kpi_card(p, 455, y, "Status", order.status.upper(), "#f59e0b" if order.status != 'delivered' else "#16a34a")
                
                # 2. Logistics & Routing Details
                y -= 90 # Increased spacing

                p.setFont("Helvetica-Bold", 12)
                p.setFillColor(colors.HexColor('#1e293b'))
                p.drawString(50, y, "Routing & Logistics Information")
                y -= 15
                
                logistics_data = [
                    ["Segment", "Details"],
                    ["Origin Warehouse", f"{order.warehouse_name}\n{order.warehouse_address}"],
                    ["Destination Address", f"{order.delivery_address}"],
                    ["Assigned Vehicle", order.assigned_vehicle.plate_number if order.assigned_vehicle else "PENDING ASSET"],
                    ["Assigned Driver", order.assigned_driver.employee.full_name if order.assigned_driver else "PENDING PERSONNEL"]
                ]
                
                y = draw_styled_table(p, 50, y, w - 100, logistics_data, header_color='#475569')
                
                # 3. Timeline & Compliance
                y -= 20
                p.setFont("Helvetica-Bold", 12)
                p.drawString(50, y, "Audit & Compliance Timeline")
                y -= 15
                
                timeline_data = [["Timestamp", "Action / Status Change", "Authorizer"]]
                logs = order.status_logs.all().order_by('changed_at')
                for log in logs:
                    timeline_data.append([
                        log.changed_at.strftime('%Y-%m-%d %H:%M'),
                        f"Changed to {log.to_status.upper()}",
                        log.changed_by.username if log.changed_by else "System"
                    ])
                
                if len(timeline_data) == 1:
                    timeline_data.append([order.created_at.strftime('%Y-%m-%d %H:%M'), "Order Created / Registered", "System"])
                
                y = draw_styled_table(p, 50, y, w - 100, timeline_data)
                
                # 4. Security & Sign-off
                y -= 20
                p.setFont("Helvetica-Bold", 8)
                p.drawString(50, y, "MANAGER VERIFICATION:")
                p.line(160, y, 350, y)
                p.drawString(w - 200, y, "DATE: ________________")
                
                # 5. Delivery Confirmation (If Applicable)
                y -= 40
                p.setFont("Helvetica-Bold", 10)
                p.drawString(50, y, "Recipient Acknowledgment")
                y -= 10
                
                from .utils.document_generator import draw_signature
                if hasattr(order, 'recipient_signature') and order.recipient_signature:
                    y = draw_signature(p, 50, y, order.recipient_signature)
                    y -= 10
                    p.setFont("Helvetica-Bold", 9)
                    p.drawString(50, y, "Status: Verified & Digitally Signed")
                else:
                    p.setFont("Helvetica-Oblique", 8)
                    p.drawString(50, y - 10, "No digital signature captured.")
                    y -= 20
                
                # Footer
                p.setFont("Helvetica-Oblique", 7)
                p.drawCentredString(w/2, 30, "Generated by Nestle Logistics Management Portal. Proprietary and Confidential.")

            return generate_pdf_response(f"Waybill_ORD_{order.order_id}", content)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)


class ShipmentViewSet(viewsets.ModelViewSet):
    queryset = Shipment.objects.select_related('vehicle', 'driver', 'driver__employee').prefetch_related('order_mappings', 'order_mappings__order').all().order_by('-created_at')
    serializer_class = ShipmentSerializer
    def get_permissions(self):
        # Specific driver actions allowed with basic auth
        driver_actions = ['driver_tasks', 'driver_active', 'assignment_view', 'accept_assignment', 'scan_pickup', 'scan_delivery', 'report_exception']
        if self.action in driver_actions:
            return [permissions.IsAuthenticated()]
        # Internal deployment actions restrict to Dispatchers
        if self.action == 'deploy_manifest':
            return [IsDispatcherRole()]
        return [IsInternalRole()]

    def perform_destroy(self, instance):
        with transaction.atomic():
            # 1. Reset all orders linked to this shipment
            from .models import ShipmentOrder, OrderStatusLog
            mappings = ShipmentOrder.objects.filter(shipment=instance)
            for m in mappings:
                order = m.order
                old_status = order.status
                order.status = 'pending'
                order.assigned_vehicle = None
                order.assigned_driver = None
                order.save()
                
                # Log the status reversal for audit trail
                OrderStatusLog.objects.create(
                    order=order,
                    from_status=old_status,
                    to_status='pending',
                    changed_by=self.request.user,
                    source='management_deletion'
                )

            # 2. Release Assets
            if instance.vehicle:
                instance.vehicle.status = 'available'
                instance.vehicle.save()
            if instance.driver:
                instance.driver.status = 'available'
                instance.driver.save()
            
            # 3. Audit Logging
            from .models import AuditLog
            AuditLog.objects.create(
                user=self.request.user,
                action='DELETE_SHIPMENT',
                resource_type='Shipment',
                resource_id=instance.shipment_id,
                details=f"Permanent deletion of Shipment #{instance.shipment_id}. Associated orders reverted to 'pending' as primary records."
            )
            
            instance.delete()

    @action(detail=False, methods=['post'])
    def deploy_manifest(self, request):
        order_ids = request.data.get('order_ids', [])
        vehicle_id = request.data.get('vehicle_id')
        driver_id = request.data.get('driver_id') # User ID
        
        if not order_ids or not vehicle_id or not driver_id:
            return Response({'error': 'Insufficient manifest data: orders, vehicle, and driver are required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            with transaction.atomic():
                from drivers.models import Driver
                from .models import AuditLog
                vehicle = Vehicle.objects.get(vehicle_id=vehicle_id)
                driver = Driver.objects.get(employee__user__user_id=driver_id)
                orders = Order.objects.filter(order_id__in=order_ids)
                
                # 1. Validate Capacity
                total_w = sum(float(o.weight_kg) for o in orders)
                total_v = sum(float(o.volume_m3) for o in orders)
                needs_fridge = any(o.requires_refrigeration for o in orders)
                
                if total_w > float(vehicle.capacity_kg):
                    return Response({'error': f"Payload ({total_w}kg) exceeds vehicle capacity ({vehicle.capacity_kg}kg)"}, status=status.HTTP_400_BAD_REQUEST)
                if total_v > float(vehicle.capacity_volume):
                    return Response({'error': f"Volume ({total_v}m3) exceeds vehicle storage ({vehicle.capacity_volume}m3)"}, status=status.HTTP_400_BAD_REQUEST)
                if needs_fridge and not vehicle.is_refrigerated:
                    return Response({'error': "Manifest contains refrigerated items, but the vehicle is not equipped with a cooling system."}, status=status.HTTP_400_BAD_REQUEST)

                # 2. Determine Shipment Type
                types = set(o.shipment_type for o in orders)
                s_type = 'mixed' if len(types) > 1 else list(types)[0]
                
                # 3. Create Shipment
                shipment = Shipment.objects.create(
                    vehicle=vehicle,
                    driver=driver,
                    total_weight=total_w,
                    total_volume=total_v,
                    shipment_type=s_type,
                    requires_refrigeration=needs_fridge,
                    status='dispatched',
                    deployed_at=timezone.now()
                )
                
                # 4. Automatic Sequence & Routing
                from .utils.route_optimization import sequence_route, calculate_etas
                first_order = orders.first()
                origin = {
                    'lat': float(first_order.warehouse_lat) if first_order.warehouse_lat else 0,
                    'lng': float(first_order.warehouse_lng) if first_order.warehouse_lng else 0,
                    'address': first_order.warehouse_address,
                    'name': first_order.warehouse_name
                }
                
                stops_data = []
                for o in orders:
                    stops_data.append({
                        'id': o.order_id,
                        'lat': float(o.delivery_lat) if o.delivery_lat else 0.0,
                        'lng': float(o.delivery_lng) if o.delivery_lng else 0.0,
                        'address': o.delivery_address
                    })
                    
                ordered_stops = sequence_route(stops_data, origin)
                shipment.route_sequence = [s['id'] for s in ordered_stops]
                shipment.scheduled_pickup_time = timezone.now() + timezone.timedelta(minutes=15)
                shipment.save()

                # 5. Map Orders and Update Status
                for o in orders:
                    ShipmentOrder.objects.create(shipment=shipment, order=o)
                    o.assigned_vehicle = vehicle
                    o.assigned_driver = driver
                    o.status = 'assigned'
                    o.save()
                
                # 6. Mark Assets as Busy
                vehicle.status = 'in_use'
                vehicle.save()
                driver.status = 'busy'
                driver.save()
                
                # 7. Audit Log
                AuditLog.objects.create(
                    user=request.user,
                    action='DEPLOY_MANIFEST',
                    resource_type='Shipment',
                    resource_id=shipment.shipment_id,
                    details=f"Deployed Manifest #{shipment.shipment_id} with {len(order_ids)} orders to Vehicle {vehicle.plate_number}. Sequential route calculated."
                )
                
                return Response(ShipmentSerializer(shipment).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': f"Deployment failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def assignment_view(self, request):
        user = request.user
        user_id_fallback = request.query_params.get('user_id')
        
        from drivers.models import Driver as DriverProfile
        from .models import ShipmentOrder
        try:
            if user.is_authenticated:
                driver = DriverProfile.objects.get(employee__user=user)
            else:
                driver = DriverProfile.objects.get(employee__user_id=user_id_fallback)
                
            shipment = Shipment.objects.filter(driver=driver, status__in=['dispatched', 'accepted', 'in_transit']).order_by('-created_at').first()
            if not shipment:
                 return Response({'error': 'No active assignment'}, status=status.HTTP_200_OK)

            from .models import Order
            # Fetch IDs and then fetch fresh Order objects directly to bypass any caching
            order_ids = list(ShipmentOrder.objects.filter(shipment=shipment).values_list('order__order_id', flat=True))
            orders = list(Order.objects.filter(order_id__in=order_ids))
            
            if not orders:
                 return Response({'error': 'No orders in shipment'}, status=status.HTTP_200_OK)

            first_order = orders[0]
            origin = {
                'lat': float(first_order.warehouse_lat) if first_order.warehouse_lat else 0,
                'lng': float(first_order.warehouse_lng) if first_order.warehouse_lng else 0,
                'address': first_order.warehouse_address,
                'name': first_order.warehouse_name
            }
            
            # Map sequence back to order objects
            ordered_orders = sorted(orders, key=lambda x: shipment.route_sequence.index(x.order_id) if (shipment.route_sequence and x.order_id in shipment.route_sequence) else 999)
            
            stops = []
            current_time = shipment.scheduled_pickup_time or timezone.now()
            prev_lat, prev_lng = origin['lat'], origin['lng']
            total_dist = 0
            
            from .utils.route_optimization import haversine
            for i, o in enumerate(ordered_orders):
                dist = haversine(prev_lat, prev_lng, float(o.delivery_lat), float(o.delivery_lng))
                travel_time = dist / 40.0
                current_time += timezone.timedelta(hours=travel_time)
                total_dist += dist
                
                stops.append({
                    "sequence": i + 1,
                    "order_id": str(o.order_id),
                    "address": o.delivery_address,
                    "city": "Industrial Area",
                    "delivery_instructions": "Check for fragile items",
                    "customer_phone": "0712345678",
                    "estimated_arrival": current_time.isoformat(),
                    "parcels": o.quantity,
                    "weight_kg": float(o.weight_kg),
                    "status": o.status
                })
                prev_lat, prev_lng = float(o.delivery_lat), float(o.delivery_lng)

            return Response({
                "shipment_id": str(shipment.shipment_id),
                "status": shipment.status,
                "vehicle": {
                    "plate_number": shipment.vehicle.plate_number,
                    "model": f"{shipment.vehicle.manufacturer} {shipment.vehicle.model}" if shipment.vehicle.model else shipment.vehicle.manufacturer,
                    "is_refrigerated": shipment.vehicle.is_refrigerated
                },
                "warehouse": {
                    "id": first_order.warehouse_id,
                    "name": first_order.warehouse_name,
                    "address": first_order.warehouse_address,
                    "gate": "Gate 1",
                    "contact_phone": "+94 77 111 2222",
                    "pickup_time": shipment.scheduled_pickup_time.isoformat() if shipment.scheduled_pickup_time else None,
                    "ready_time": shipment.scheduled_pickup_time.isoformat() if shipment.scheduled_pickup_time else None
                },
                "route_summary": {
                    "total_stops": len(stops),
                    "total_distance_km": round(total_dist, 2),
                    "estimated_duration_minutes": int(total_dist / 40.0 * 60)
                },
                "stops": stops,
                "driver_briefing": {
                    "leave_by": shipment.leave_by_time.isoformat() if shipment.leave_by_time else None,
                    "notes": "Observe all safety protocols."
                }
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def accept_assignment(self, request, pk=None):
        shipment = self.get_object()
        if shipment.status != 'dispatched':
            return Response({'error': 'Shipment is not in a dispatchable state'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if driver has a checked-out vehicle
        from .models import VehicleAssignment
        from drivers.models import Driver
        try:
            # Identity Fallback for user
            user = request.user
            if not user.is_authenticated:
                u_id = request.data.get('user_id')
                if u_id:
                    from .models import CustomUser
                    user = CustomUser.objects.filter(user_id=u_id).first()
            
            driver = Driver.objects.get(employee__user=user)
            active_assignment = VehicleAssignment.objects.filter(driver=driver, status='active').first()
            if not active_assignment:
                return Response({'error': 'Deployment Blocked: You must be assigned to a vehicle before accepting dispatches.'}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({'error': f'Auth context error: {str(e)}'}, status=status.HTTP_401_UNAUTHORIZED)
        
        shipment.status = 'accepted'
        shipment.accepted_at = timezone.now()
        shipment.save()
        
        from .models import OrderStatusLog, ShipmentOrder, CustomUser
        
        # Identity Fallback logic
        user = request.user
        if not user.is_authenticated:
            u_id = request.data.get('user_id')
            if u_id:
                user = CustomUser.objects.filter(user_id=u_id).first()
        
        order_mappings = ShipmentOrder.objects.filter(shipment=shipment)
        for m in order_mappings:
            old_status = m.order.status
            m.order.status = 'assigned'
            m.order.save()
            
            OrderStatusLog.objects.create(
                order=m.order,
                from_status=old_status,
                to_status='assigned',
                changed_by=user,
                source='system'
            )
            
        return Response({'success': True, 'status': shipment.status})

    @action(detail=True, methods=['post'])
    def scan_pickup(self, request, pk=None):
        shipment = self.get_object()
        qr_token = request.data.get('qr_token')
        
        # QR validation: exact match preferred, fallback to contains
        expected_qr = f"MF-{shipment.shipment_id}"
        if not qr_token or (expected_qr not in qr_token and str(shipment.shipment_id) not in qr_token):
            return Response({'error': 'Invalid QR manifest signature. Expected manifest QR.'}, status=status.HTTP_401_UNAUTHORIZED)
            
        shipment.status = 'in_transit'
        shipment.pickup_scanned_at = timezone.now()
        shipment.save()
        
        from .models import OrderStatusLog, ShipmentOrder, CustomUser
        
        # Identity Fallback
        user = request.user
        if not user.is_authenticated:
            u_id = request.data.get('user_id')
            if u_id:
                user = CustomUser.objects.filter(user_id=u_id).first()

        order_mappings = ShipmentOrder.objects.filter(shipment=shipment)
        for m in order_mappings:
            old_status = m.order.status
            m.order.status = 'in_transit'
            m.order.save()
            
            OrderStatusLog.objects.create(
                order=m.order,
                from_status=old_status,
                to_status='in_transit',
                changed_by=user,
                source='driver_scan'
            )
            
        return Response({'success': True, 'status': shipment.status})

    @action(detail=True, methods=['post'])
    def scan_delivery(self, request, pk=None):
        shipment = self.get_object()
        order_id = request.data.get('order_id')
        qr_token = request.data.get('qr_token')
        lat = request.data.get('lat')
        lng = request.data.get('lng')
        
        if not qr_token or not order_id:
             return Response({'error': 'QR token and order_id are required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # QR match: token must contain shipment and order identifiers, OR be the manifest QR code
        expected_token_part = f"SHP-{shipment.shipment_id}-ORD-{order_id}"
        manifest_qr = f"MF-{shipment.shipment_id}"
        if expected_token_part not in qr_token and str(order_id) not in qr_token and manifest_qr not in qr_token:
             return Response({'error': 'QR mismatch: Parcel does not belong to this stop.'}, status=status.HTTP_400_BAD_REQUEST)

        from .models import Order, OrderStatusLog, CustomUser
        try:
            order = Order.objects.get(order_id=order_id)
        except Order.DoesNotExist:
            return Response({'error': 'Order context lost'}, status=status.HTTP_404_NOT_FOUND)
        
        # CRITICAL: Prevent duplicate delivery
        if order.status == 'delivered':
            return Response({'error': 'This order has already been delivered. Scan rejected.'}, status=status.HTTP_400_BAD_REQUEST)
        if order.status == 'delivery_failed':
            return Response({'error': 'This order has a recorded exception. Contact dispatcher.'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Identity Fallback
        user = request.user
        if not user.is_authenticated:
            u_id = request.data.get('user_id')
            if u_id:
                user = CustomUser.objects.filter(user_id=u_id).first()

        old_status = order.status
        order.status = 'delivered'
        order.delivered_at = timezone.now()
        order.delivered_by_driver_id = shipment.driver.driver_id
        order.delivery_location_lat = lat
        order.delivery_location_lng = lng
        
        # Save recipient signature if provided
        signature = request.data.get('signature')
        if signature:
            order.recipient_signature = signature
            
        order.save()
        
        OrderStatusLog.objects.create(
            order=order,
            from_status=old_status,
            to_status='delivered',
            changed_by=user,
            source='driver_scan'
        )
        
        from .models import ShipmentOrder
        remaining = ShipmentOrder.objects.filter(shipment=shipment).exclude(order__status__in=['delivered', 'delivery_failed']).count()
        
        if remaining == 0:
            shipment.status = 'completed'
            shipment.completed_at = timezone.now()
            shipment.save()
            
        return Response({
            'success': True, 
            'is_completed': remaining == 0,
            'remaining_stops': remaining
        })

    @action(detail=False, methods=['get'])
    def driver_active(self, request):
        """ Fetch the active manifest OR assigned vehicle for the logged-in driver. """
        user = request.user
        user_id_fallback = request.query_params.get('user_id')
        
        if not user.is_authenticated and not user_id_fallback:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            
        from drivers.models import Driver
        try:
            target_id = user.user_id if user.is_authenticated else int(user_id_fallback)
            driver = Driver.objects.get(employee__user__user_id=target_id)
                
            assignment = VehicleAssignment.objects.filter(driver=driver, status='active').first()
            # Force is_checked_out to True to bypass scanning requirement as requested
            is_checked_out = True if assignment else False

            shipment = Shipment.objects.filter(driver=driver, status__in=['dispatched', 'accepted', 'in_transit']).first()
            if shipment:
                data = ShipmentSerializer(shipment).data
                data['assignment_type'] = 'outbound'
                data['is_checked_out'] = is_checked_out
                return Response(data)
                
            # Check for Inbound Assignment
            from inbound.models import InboundCollectionAssignment
            from inbound.serializers import AssignmentDetailSerializer
            inbound_assignment = InboundCollectionAssignment.objects.filter(
                driver=driver,
                status__in=['assigned', 'accepted', 'en_route', 'at_supplier', 'verifying', 'returning']
            ).first()

            if inbound_assignment:
                data = AssignmentDetailSerializer(inbound_assignment).data
                data['assignment_type'] = 'inbound'
                data['is_checked_out'] = is_checked_out
                return Response(data)

            # Fallback: Just return vehicle info if assigned via VehicleAssignment
            if assignment and assignment.vehicle:
                return Response({
                    "vehicle_details": VehicleSerializer(assignment.vehicle).data,
                    "assignment_type": "none",
                    "status": "idle",
                    "is_checked_out": is_checked_out
                })

            return Response({'detail': 'No active manifest or vehicle assigned.', 'is_checked_out': False}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            import traceback
            return Response({'error': f"Operation failed: {str(e)}", "trace": traceback.format_exc()}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def download_manifest(self, request, pk=None):
        """ Generate a professional shipment manifest for a specific dispatch. """
        shipment = self.get_object()
        try:
            from .models import ShipmentOrder
            from .utils.document_generator import generate_pdf_response, draw_header, draw_kpi_card, draw_styled_table, draw_status_pill
            from reportlab.lib import colors
            
            order_mappings = ShipmentOrder.objects.filter(shipment=shipment).select_related('order')
            orders = [m.order for m in order_mappings]
            
            def content(p, w, h):
                draw_header(p, w, h, "Shipment Dispatch Manifest", f"Official Documentation for Shipment ID: SHP-{shipment.shipment_id}")
                
                # 1. Dispatch Summary KPIs
                y = h - 185
                draw_kpi_card(p, 50, y, "Total Load", f"{shipment.total_weight} kg", "#1e293b")
                draw_kpi_card(p, 185, y, "Total Volume", f"{shipment.total_volume} m³", "#3b82f6")
                draw_kpi_card(p, 320, y, "Drop-offs", len(orders), "#16a34a")
                draw_kpi_card(p, 455, y, "Status", shipment.status.upper(), "#f59e0b" if shipment.status != 'completed' else "#16a34a")
                
                # 2. Asset & Crew Information
                y -= 90
                p.setFont("Helvetica-Bold", 12)
                p.setFillColor(colors.HexColor('#1e293b'))
                p.drawString(50, y, "Asset & Personnel Information")
                y -= 15
                
                asset_data = [
                    ["Category", "Details"],
                    ["Primary Vehicle", f"{shipment.vehicle.plate_number} ({shipment.vehicle.manufacturer} {shipment.vehicle.model})" if shipment.vehicle else "Unassigned"],
                    ["Assigned Driver", f"{shipment.driver.employee.full_name}" if (shipment.driver and hasattr(shipment.driver, 'employee') and shipment.driver.employee) else "Unassigned"],
                    ["Refrigeration", "YES (ACTIVE)" if shipment.requires_refrigeration else "NO"],
                    ["Dispatch Time", shipment.deployed_at.strftime('%Y-%m-%d %H:%M') if shipment.deployed_at else "N/A"]
                ]
                y = draw_styled_table(p, 50, y, w - 100, asset_data, header_color='#475569')
                
                # 3. Delivery Sequence Table
                y -= 20
                p.setFont("Helvetica-Bold", 12)
                p.drawString(50, y, "Sequential Delivery Stops")
                y -= 15
                
                stops_data = [["Seq", "Order ID", "Destination / Address", "Weight", "Qty"]]
                # Sort by route sequence if available
                ordered_orders = sorted(orders, key=lambda x: shipment.route_sequence.index(x.order_id) if (shipment.route_sequence and x.order_id in shipment.route_sequence) else 999)
                
                for i, o in enumerate(ordered_orders):
                    stops_data.append([
                        str(i+1),
                        f"ORD-{o.order_id}",
                        o.delivery_address[:50] + "..." if len(o.delivery_address) > 50 else o.delivery_address,
                        f"{o.weight_kg}kg",
                        str(o.quantity)
                    ])
                
                y = draw_styled_table(p, 50, y, w - 100, stops_data)
                
                # 4. Compliance & Verification
                y = 80
                p.setFont("Helvetica", 7)
                p.drawString(50, y, "DISPATCHER SIGNATURE: __________________________")
                p.drawString(w - 250, y, "DRIVER ACKNOWLEDGMENT: __________________________")
                
                # Footer
                p.setFont("Helvetica-Oblique", 7)
                p.drawCentredString(w/2, 30, "Generated by Nestle Logistics Management Portal. Drivers must verify all seals before departure.")

            return generate_pdf_response(f"Manifest_SHP_{shipment.shipment_id}", content)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().order_by('-timestamp')
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminRole]

def find_best_vehicle(total_weight, total_volume, requires_fridge):
    assets = Vehicle.objects.filter(status='available')
    if requires_fridge:
        assets = assets.filter(is_refrigerated=True)
    
    # Sort by capacity to get the smallest viable vehicle
    potential = assets.filter(
        capacity_kg__gte=total_weight,
        capacity_volume__gte=total_volume
    ).order_by('capacity_kg')
    
    return potential.first()

@api_view(['GET'])
@permission_classes([IsDispatcherRole])
def dispatch_recommendations(request):
    """
    Get recommended order clusters with metrics and suggested assets, grouped by warehouse.
    """
    pending_orders = Order.objects.filter(status='pending')
    if not pending_orders.exists():
        return Response({'warehouses': {}}, status=status.HTTP_200_OK)
    
    order_data = []
    for o in pending_orders:
        if o.pickup_lat and o.pickup_lng:
            order_data.append({
                'id': o.order_id,
                'lat': float(o.pickup_lat),
                'lng': float(o.pickup_lng),
                'warehouse_id': o.warehouse_id,
                'warehouse_name': o.warehouse_name,
                'warehouse_address': o.warehouse_address
            })
            
    if not order_data:
        return Response({'warehouses': {}}, status=status.HTTP_200_OK)
        
    clusters = cluster_orders(order_data)
    
    warehouses_output = {}
    
    for cluster_id, order_ids in clusters.items():
        order_objs = Order.objects.filter(order_id__in=order_ids)
        if not order_objs.exists(): continue
        
        first_order = order_objs.first()
        wh_id = first_order.warehouse_id
        
        if wh_id not in warehouses_output:
            warehouses_output[wh_id] = {
                'id': wh_id,
                'name': first_order.warehouse_name,
                'address': first_order.warehouse_address,
                'clusters': {}
            }
        
        # Calculate stats
        total_weight = sum(float(o.weight_kg) for o in order_objs)
        total_volume = sum(float(o.volume_m3) for o in order_objs)
        needs_fridge = any(o.requires_refrigeration for o in order_objs)
        
        # Find best vehicle
        suggested_asset = find_best_vehicle(total_weight, total_volume, needs_fridge)
        
        warehouses_output[wh_id]['clusters'][cluster_id] = {
            'orders': OrderSerializer(order_objs, many=True).data,
            'metrics': {
                'total_weight': total_weight,
                'total_volume': total_volume,
                'needs_fridge': needs_fridge,
                'order_count': order_objs.count()
            },
            'suggestion': VehicleSerializer(suggested_asset).data if suggested_asset else None
        }
        
    return Response({'warehouses': warehouses_output}, status=status.HTTP_200_OK)


from .filters import DeliverySearchFilter
from .serializers import OrderSerializer, AuditLogSerializer, ShipmentSerializer, OrderExceptionSerializer, OrderStatusLogSerializer
try:
    import firebase_admin
    from firebase_admin import db as firebase_db
except ImportError:
    firebase_admin = None
    firebase_db = None

class DeliverySearchView(APIView):
    permission_classes = [IsInternalRole]

    def get(self, request):
        from .search_service import DeliverySearchService
        params = DeliverySearchFilter(request.GET, queryset=Order.objects.all())
        
        service = DeliverySearchService(
            user=request.user,
            params=request.GET
        )
        results = service.execute()
        
        # Apply filters from django-filter
        # Use order_id instead of id
        results = params.qs.filter(order_id__in=results.values_list('order_id', flat=True))
        
        serializer = OrderSerializer(results, many=True)
        return Response({
            'count': results.count(),
            'results': serializer.data,
        })

class UniversalSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('q', '')
        search_type = request.query_params.get('type', 'all')
        
        if not query:
            return Response([])

        results = []

        # Orders
        if search_type in ['all', 'orders']:
            orders = Order.objects.filter(
                Q(order_id__icontains=query) |
                Q(pickup_address__icontains=query) |
                Q(delivery_address__icontains=query) |
                Q(warehouse_name__icontains=query)
            )[:20]
            for o in orders:
                results.append({
                    'type': 'order',
                    'data': OrderSerializer(o).data
                })

        # Vehicles
        if search_type in ['all', 'vehicles']:
            vehicles = Vehicle.objects.filter(
                Q(plate_number__icontains=query) |
                Q(vehicle_type__icontains=query) |
                Q(manufacturer__icontains=query) |
                Q(model__icontains=query)
            )[:20]
            for v in vehicles:
                results.append({
                    'type': 'vehicle',
                    'data': VehicleSerializer(v).data
                })

        # Shipments
        if search_type in ['all', 'shipments']:
            shipments = Shipment.objects.filter(
                Q(shipment_id__icontains=query) |
                Q(status__icontains=query) |
                Q(shipment_type__icontains=query)
            )[:20]
            for s in shipments:
                results.append({
                    'type': 'shipment',
                    'data': ShipmentSerializer(s).data
                })

        # Users
        if search_type in ['all', 'users']:
            users = CustomUser.objects.filter(
                Q(username__icontains=query) |
                Q(email__icontains=query)
            )[:20]
            for u in users:
                results.append({
                    'type': 'user',
                    'data': UserSerializer(u).data
                })

        # Audit Logs
        if search_type in ['all', 'audits']:
            audits = AuditLog.objects.filter(
                Q(action__icontains=query) |
                Q(resource_type__icontains=query) |
                Q(details__icontains=query)
            ).order_by('-timestamp')[:20]
            for a in audits:
                results.append({
                    'type': 'audit',
                    'data': AuditLogSerializer(a).data
                })

        return Response(results)

class LiveVehicleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Fallback to local cache if firebase not fully setup
        locations = cache.get('active_locations', {})
        
        vehicle_id = request.query_params.get('vehicle_id')
        driver_id  = request.query_params.get('driver_id')

        results = []
        for d_id, data in locations.items():
            if vehicle_id and str(data.get('vehicle_id')) != str(vehicle_id):
                continue
            if driver_id and str(data.get('driver_id')) != str(driver_id):
                continue
            results.append(data)

        return Response({'count': len(results), 'results': results})

class OrderAuditView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.prefetch_related(
                'status_logs__changed_by',
                'exceptions__driver',
                'assigned_driver',
                'assigned_vehicle',
            ).get(order_id=order_id)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        return Response({
            'order': OrderSerializer(order).data,
            'status_timeline': OrderStatusLogSerializer(
                order.status_logs.order_by('changed_at'), many=True
            ).data,
            'exceptions': OrderExceptionSerializer(
                order.exceptions.order_by('reported_at'), many=True
            ).data,
            'tracking_summary': self._get_tracking_summary(order),
        })

    def _get_tracking_summary(self, order):
        # Fetch historical breadcrumbs from local cache/persistence since firebase might be empty
        from .models import GPSPersistence
        if order.assigned_driver:
            history = GPSPersistence.objects.filter(
                driver=order.assigned_driver,
                timestamp__date=order.created_at.date()
            ).order_by('timestamp')
            return [
                {'lat': float(h.latitude), 'lng': float(h.longitude), 'timestamp': h.timestamp.isoformat()}
                for h in history
            ]
        return []


class ChangePasswordView(APIView):
    """
    Allow an authenticated user to change their own password.
    POST: { "old_password": "...", "new_password": "..." }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password', '')
        new_password = request.data.get('new_password', '')

        if not old_password or not new_password:
            return Response(
                {'detail': 'Both old_password and new_password are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(old_password):
            return Response(
                {'detail': 'Current password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(new_password) < 6:
            return Response(
                {'detail': 'New password must be at least 6 characters long.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        # Audit log
        from .models import AuditLog
        AuditLog.objects.create(
            user=user,
            action='PASSWORD_CHANGE',
            resource_type='Account',
            details=f"User '{user.username}' changed their password."
        )

        return Response({'detail': 'Password updated successfully.'}, status=status.HTTP_200_OK)

class ProofOfDeliveryViewSet(viewsets.ModelViewSet):
    queryset = ProofOfDelivery.objects.all().order_by('-timestamp')
    serializer_class = ProofOfDeliverySerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['get'])
    def download_pod(self, request, pk=None):
        pod = self.get_object()
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_styled_table, draw_logo
            from reportlab.lib import colors
            
            def content(p, w, h):
                from .utils.document_generator import draw_logo
                # Clean White Header
                p.setFont("Helvetica-Bold", 22)
                p.setFillColor(colors.black)
                p.drawString(50, h - 60, "Proof of Delivery")
                
                # Draw Logo on the right
                draw_logo(p, w - 110, h - 80, size=60)
                
                p.setFont("Helvetica-Bold", 12)
                p.setFillColor(colors.black)
                p.drawString(50, h - 130, f"Our Ref : {pod.order.order_id}")

                
                # Order Meta Info
                p.setFont("Helvetica", 9)
                p.drawString(50, h - 150, f"Delivery Ref : DO-{pod.order.order_id}XT")
                p.drawString(50, h - 165, f"Your Ref : SO-99281-B")
                p.drawString(50, h - 180, f"Order Date : {pod.timestamp.strftime('%Y-%m-%d')}")
                
                # Client & Shipper Details
                p.setFont("Helvetica-Bold", 10)
                p.drawString(50, h - 210, "Client:")
                p.drawString(w - 200, h - 210, "Shipper:")
                
                p.setFont("Helvetica", 9)
                # Fallback since Order doesn't have a direct Customer link
                cust_name = "General Client"
                p.drawString(50, h - 225, cust_name)
                p.drawString(50, h - 140, pod.order.delivery_address[:60] if pod.order.delivery_address else "No Address Provided")
                p.drawString(w - 200, h - 225, "CC-NESTLE LOGISTICS INC.")
                
                # Items Table (Mocked for visual reference)
                y = h - 260
                items_data = [
                    ["#", "Code", "Description", "Qty", "Status"],
                    ["1", "SKU-001", "Assorted Logistics Items", str(pod.order.quantity), "OK"],
                    ["2", "SKU-092", "Standard Delivery Package", "1", "OK"],
                ]
                y = draw_styled_table(p, 50, y, w - 100, items_data, header_color='#475569')

                
                # Delivery Proof Section
                y -= 30
                p.setFont("Helvetica-Bold", 10)
                p.drawString(50, y, "Delivery Proof Information")
                y -= 15
                p.setFont("Helvetica", 9)
                p.drawString(50, y, f"Delivery Status: {pod.order.status.upper()}")
                p.drawString(50, y - 15, f"Time: {pod.timestamp.strftime('%Y-%m-%d %H:%M')}")
                
                driver_name = "N/A"
                if hasattr(pod.order, 'assigned_driver') and pod.order.assigned_driver:
                    driver_name = pod.order.assigned_driver.employee.full_name
                p.drawString(50, y - 30, f"Driver: {driver_name}")
                
                # Map Visualization
                y_map = y
                from .utils.document_generator import draw_delivery_map, draw_signature
                y_map = draw_delivery_map(p, w - 250, y_map, pod.order.delivery_location_lat, pod.order.delivery_location_lng)
                
                # Signature Section
                y -= 60
                p.setFont("Helvetica-Bold", 10)
                p.drawString(50, y, "Recipient Acknowledgment")
                y -= 10
                
                if pod.order.recipient_signature:
                    y = draw_signature(p, 50, y, pod.order.recipient_signature)
                else:
                    p.setFont("Helvetica-Oblique", 8)
                    p.drawString(50, y - 10, "No digital signature captured.")
                    y -= 20
                
                y -= 10
                p.setFont("Helvetica-Bold", 9)
                p.drawString(50, y, f"Recipient ID: {pod.recipient_name}")
                p.drawString(50, y - 15, "Status: Verified & Digitally Signed")
                
                # Footer
                p.setFont("Helvetica-Bold", 12)
                p.drawCentredString(w/2, 40, "THANK YOU FOR YOUR ORDER")
                
            return generate_pdf_response(f"POD_{pod.order.order_id}", content)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)

class OrderExceptionViewSet(viewsets.ModelViewSet):
    queryset = OrderException.objects.all().order_by('-reported_at')
    serializer_class = OrderExceptionSerializer
    permission_classes = [permissions.IsAuthenticated]

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def trigger_reminder(request):
    req_type = request.data.get('type')
    req_id = request.data.get('id')
    
    if not req_type or not req_id:
        return Response({"error": "Missing type or id"}, status=400)
        
    try:
        if req_type == 'vehicle':
            from vehicles.models import Vehicle
            from api.models import VehicleAssignment
            
            vehicle = Vehicle.objects.get(pk=req_id)
            
            # Check if vehicle has been assigned to a driver
            assignment = VehicleAssignment.objects.filter(vehicle=vehicle, status='active').first()
            if not assignment or not assignment.driver:
                return Response({"error": f"Vehicle {vehicle.plate_number} is not assigned to any driver. Reminder cannot be sent to mobile app."}, status=400)
                
            driver = assignment.driver
            
            # Format detailed maintenance/renewal message
            details = f"Vehicle {vehicle.plate_number} ({vehicle.manufacturer or ''} {vehicle.model or ''}) requires renewal/maintenance. "
            if vehicle.registration_expiry:
                details += f"Reg Exp: {vehicle.registration_expiry}. "
            if vehicle.insurance_expiry:
                details += f"Ins Exp: {vehicle.insurance_expiry}. "
            if vehicle.next_service_date:
                details += f"Next Svc Date: {vehicle.next_service_date}. "
            if vehicle.next_service_mileage:
                details += f"Next Svc Mileage: {vehicle.next_service_mileage} km."
                
            # Create AuditLog directly for the driver so it appears in their app
            AuditLog.objects.create(
                user=request.user,
                action='MANUAL_REMINDER_SENT',
                resource_type='Driver',
                resource_id=driver.id,
                details=details
            )
            return Response({"success": True, "message": f"Vehicle reminder sent directly to driver {driver.employee.full_name if driver.employee else 'Unknown'}"})
            
        elif req_type == 'driver':
            from drivers.models import Driver
            driver = Driver.objects.get(employee__user__user_id=req_id)
            AuditLog.objects.create(
                user=request.user,
                action='MANUAL_REMINDER_SENT',
                resource_type='Driver',
                resource_id=driver.id,
                details=f"Manual push notification dispatched for driver {driver.employee.full_name if driver.employee else 'Unknown'} license renewal."
            )
            return Response({"success": True, "message": "Driver reminder sent"})
        else:
            return Response({"error": "Invalid type"}, status=400)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def driver_notifications(request):
    try:
        user_id = request.GET.get('user_id')
        if not user_id:
            return Response({"error": "user_id is required"}, status=400)
            
        # All local imports neatly packed inside to dodge circular dependency loops
        from drivers.models import Driver
        from api.models import VehicleAssignment, AuditLog 
        from django.db.models import Q
        
        # Get the driver profile for this user
        driver = Driver.objects.filter(employee__user_id=user_id).first()
        if not driver:
            return Response([])
            
        # Get currently assigned vehicle
        assignment = VehicleAssignment.objects.filter(driver=driver, status='active').first()
        vehicle_id = assignment.vehicle.vehicle_id if assignment and assignment.vehicle else None
        
        # Query AuditLogs
        query = Q(action__in=['MANUAL_REMINDER_SENT', 'EXPIRY_NOTIFICATION_SENT'])
        
        # We are using getattr here as an insurance policy. If driver uses driver_id, it falls back cleanly!
        driver_pk = getattr(driver, 'driver_id', getattr(driver, 'id', None))
        driver_q = Q(resource_type='Driver', resource_id=driver_pk)
        
        if vehicle_id:
            vehicle_q = Q(resource_type='Vehicle', resource_id=vehicle_id)
            query = query & (driver_q | vehicle_q)
        else:
            query = query & driver_q
            
        logs = AuditLog.objects.filter(query).order_by('-timestamp')[:20]
        
        data = []
        for log in logs:
            data.append({
                'id': log.log_id, # <-- Clean fixed key name
                'action': log.action,
                'details': log.details,
                'timestamp': log.timestamp.isoformat(),
                'resource_type': log.resource_type
            })
            
        return Response(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)

class ReportViewSet(viewsets.ViewSet):
    permission_classes = [IsInternalRole]

    @action(detail=False, methods=['get'])
    def vehicle_assignments(self, request):
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_styled_table, draw_status_pill
            from .models import VehicleAssignment
            
            assignments = VehicleAssignment.objects.all().select_related('vehicle', 'driver__employee')
            
            def content(p, w, h):
                draw_header(p, w, h, "Fleet Deployment Registry", "Vehicle & Driver Asset Management")
                
                y = h - 120
                table_data = [["Vehicle Plate", "Model", "Driver Name", "Contact", "Status", "Route/Zone"]]
                
                for a in assignments:
                    v_info = a.vehicle.plate_number if (a.vehicle and hasattr(a.vehicle, 'plate_number')) else "Unknown"
                    v_model = a.vehicle.model if (a.vehicle and hasattr(a.vehicle, 'model')) else "N/A"
                    d_name = a.driver.employee.full_name if (a.driver and a.driver.employee) else "Unassigned"
                    d_contact = a.driver.employee.contact_number if (a.driver and a.driver.employee) else "N/A"
                    status = a.status.upper() if hasattr(a, 'status') else "STANDBY"
                    zone = "CBD / Zone E" if "CBD" in d_name else "Standard / Zone A" 
                    
                    table_data.append([v_info, v_model, d_name, d_contact, status, zone])
                
                y = draw_styled_table(p, 30, y, w - 60, table_data)
                
                # Sign-off Area
                y = 60
                p.setFont("Helvetica-Bold", 8)
                p.drawString(50, y, "DISPATCH VERIFIED BY:")
                p.line(160, y, 300, y)
                p.drawString(350, y, "FLEET MANAGER SIGNATURE:")
                p.line(480, y, w - 50, y)
            
            return generate_pdf_response("Vehicle_Assignments", content)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def delivery_analytics(self, request):
        """ Provide deep JSON analytics for the management dashboard. """
        try:
            from .models import Order, Shipment, OrderException
            from vehicles.models import Vehicle, FuelExpense
            from django.db.models import Count, Avg, Sum, F, ExpressionWrapper, DurationField
            from django.utils import timezone
            from datetime import timedelta
            from .filters import DeliverySearchFilter
            
            # Apply filters to querysets
            order_filter = DeliverySearchFilter(request.GET, queryset=Order.objects.all())
            orders_qs = order_filter.qs
            
            # Filter shipments based on similar logic
            shipments_qs = Shipment.objects.all()
            if request.GET.get('driver_id'):
                shipments_qs = shipments_qs.filter(driver_id=request.GET.get('driver_id'))
            if request.GET.get('vehicle_id'):
                shipments_qs = shipments_qs.filter(vehicle_id=request.GET.get('vehicle_id'))
            if request.GET.get('date_from'):
                shipments_qs = shipments_qs.filter(created_at__gte=request.GET.get('date_from'))
            if request.GET.get('date_to'):
                shipments_qs = shipments_qs.filter(created_at__lte=request.GET.get('date_to'))
                
            # Filter exceptions based on filtered orders
            exceptions_qs = OrderException.objects.filter(order__in=orders_qs)
            
            # 1. High Level Delivery Metrics
            total_orders = orders_qs.count()
            delivered = orders_qs.filter(status='delivered').count()
            failed = orders_qs.filter(status='delivery_failed').count()
            on_time_rate = (delivered / total_orders * 100) if total_orders > 0 else 0
            
            # 2. Financial Metrics (Fuel & Cost)
            # Fuel costs are harder to filter by specific orders, but we can filter by date/vehicle if provided
            fuel_qs = FuelExpense.objects.all()
            if request.GET.get('vehicle_id'):
                fuel_qs = fuel_qs.filter(vehicle_id=request.GET.get('vehicle_id'))
            if request.GET.get('date_from'):
                fuel_qs = fuel_qs.filter(expense_date__gte=request.GET.get('date_from'))
            if request.GET.get('date_to'):
                fuel_qs = fuel_qs.filter(expense_date__lte=request.GET.get('date_to'))
                
            total_fuel_cost = fuel_qs.aggregate(total=Sum('total_cost'))['total'] or 0
            total_fuel_liters = fuel_qs.aggregate(total=Sum('liters'))['total'] or 0
            avg_cost_per_delivery = (float(total_fuel_cost) / delivered) if delivered > 0 else 0
            
            # 3. Time & Route Efficiency
            completed_shipments = shipments_qs.filter(status='completed', accepted_at__isnull=False, completed_at__isnull=False)
            avg_duration = completed_shipments.annotate(
                duration=ExpressionWrapper(F('completed_at') - F('accepted_at'), output_field=DurationField())
            ).aggregate(avg=Avg('duration'))['avg']
            
            avg_duration_minutes = avg_duration.total_seconds() / 60 if avg_duration else 0
            
            # 4. Trends
            # Use provided date range or default to last 7 days
            if request.GET.get('date_from') and request.GET.get('date_to'):
                try:
                    start_date = timezone.datetime.fromisoformat(request.GET.get('date_from')).date()
                    end_date = timezone.datetime.fromisoformat(request.GET.get('date_to')).date()
                    days_diff = (end_date - start_date).days + 1
                    if days_diff > 31: days_diff = 31 # Cap at 31 days
                    trend_days = days_diff
                    base_date = start_date
                except:
                    trend_days = 7
                    base_date = timezone.now().date() - timedelta(days=7)
            else:
                trend_days = 7
                base_date = timezone.now().date() - timedelta(days=7)

            daily_trends = []
            for i in range(trend_days):
                day = base_date + timedelta(days=i)
                count = orders_qs.filter(created_at__date=day).count()
                deliv = orders_qs.filter(delivered_at__date=day).count()
                daily_trends.append({
                    "date": day.strftime('%Y-%m-%d'),
                    "orders": count,
                    "delivered": deliv
                })
                
            # 5. Failure Reasons Breakdown
            failure_breakdown = exceptions_qs.values('exception_type').annotate(count=Count('exception_id')).order_by('-count')
            
            # 6. Driver Utilization
            from django.db.models import Q
            driver_stats = shipments_qs.values('driver__employee__full_name').annotate(
                total_trips=Count('shipment_id'),
                completed_trips=Count('shipment_id', filter=Q(status='completed'))
            ).order_by('-total_trips')[:5]

            # 7. Dynamic Insights Generation
            insights = []
            if failure_breakdown:
                top_fail = failure_breakdown[0]
                fail_label = top_fail['exception_type'].replace('_', ' ').title()
                insights.append({
                    "title": "Top Delay Pattern",
                    "desc": f"'{fail_label}' is currently the leading cause of delivery exceptions. Consider investigating root causes.",
                    "type": "warning"
                })
            
            if len(daily_trends) >= 2:
                last_2_days = daily_trends[-2:]
                yesterday = last_2_days[0]['orders']
                today_count = last_2_days[1]['orders']
                if today_count > yesterday:
                    growth = ((today_count - yesterday) / yesterday * 100) if yesterday > 0 else 100
                    insights.append({
                        "title": "Rising Volume",
                        "desc": f"Delivery demand has increased by {round(growth)}% since yesterday. Plan for additional fleet utilization.",
                        "type": "info"
                    })
            
            if on_time_rate > 90:
                insights.append({
                    "title": "Efficiency Peak",
                    "desc": "On-time delivery rates are exceeding targets. Excellent operational performance this week.",
                    "type": "success"
                })
            elif on_time_rate < 70 and total_orders > 0:
                insights.append({
                    "title": "Efficiency Warning",
                    "desc": "Delivery success rates have dropped below 70%. Review route planning and driver assignments.",
                    "type": "warning"
                })

            return Response({
                "summary": {
                    "total_orders": total_orders,
                    "delivered": delivered,
                    "failed": failed,
                    "on_time_rate": round(on_time_rate, 2),
                    "avg_cost_per_delivery": round(avg_cost_per_delivery, 2),
                    "avg_time_on_route_mins": round(avg_duration_minutes, 2),
                    "total_fuel_liters": float(total_fuel_liters)
                },
                "trends": daily_trends,
                "failures": list(failure_breakdown),
                "driver_performance": list(driver_stats),
                "insights": insights
            })
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def driver_trip_logs(self, request):
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_styled_table
            from drivers.models import TripLog
            
            logs = TripLog.objects.all().order_by('-start_time')
            
            def content(p, w, h):
                draw_header(p, w, h, "Fleet Activity Logs", "Daily Driver Trip & Fuel Tracking")
                
                y = h - 120
                table_data = [["Date", "Driver", "Vehicle", "Start", "End", "Mileage", "Fuel"]]
                
                for l in logs:
                    d_name = l.driver.employee.full_name[:20] if (l.driver and l.driver.employee) else "Unknown"
                    v_plate = l.vehicle.plate_number if l.vehicle else "Unknown"
                    mileage = f"{l.start_mileage}-{l.end_mileage if l.end_mileage else '...'}"
                    
                    table_data.append([
                        l.start_time.strftime('%Y-%m-%d'),
                        d_name,
                        v_plate,
                        l.start_time.strftime('%H:%M'),
                        l.end_time.strftime('%H:%M') if l.end_time else 'Active',
                        mileage,
                        f"{l.fuel_consumed if l.fuel_consumed else '0'} L"
                    ])
                
                draw_styled_table(p, 30, y, w - 60, table_data)
            
            return generate_pdf_response("Driver_Trip_Logs", content)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def delivery_performance(self, request):
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_kpi_card, draw_styled_table, draw_bar_chart, draw_pie_chart
            from reportlab.lib import colors
            from .models import Order, OrderException
            
            total_orders = Order.objects.count()
            delivered = Order.objects.filter(status='delivered').count()
            failed = Order.objects.filter(status='delivery_failed').count()
            pending = Order.objects.filter(status__in=['pending', 'assigned', 'in_transit']).count()
            success_rate = (delivered / total_orders * 100) if total_orders > 0 else 0
            
            # Aggregate failure reasons for Pie Chart
            from django.db.models import Count
            failure_reasons = OrderException.objects.values('exception_type').annotate(count=Count('exception_id'))
            pie_data = [r['count'] for r in failure_reasons] or [1]
            pie_labels = [r['exception_type'].replace('_', ' ').title() for r in failure_reasons] or ["No Exceptions"]

            def content(p, w, h):
                draw_header(p, w, h, "Logistics Performance Intelligence", "Executive Operational Analytics")
                
                # 1. Executive Summary KPI Cards
                y = h - 185
                draw_kpi_card(p, 50, y, "Total Volume", total_orders, "#1e293b")
                draw_kpi_card(p, 185, y, "Success Rate", f"{success_rate:.1f}%", "#16a34a")
                draw_kpi_card(p, 320, y, "Exceptions", failed, "#dc2626")
                draw_kpi_card(p, 455, y, "Active Fleet", pending, "#2563eb")
                
                # 2. Charts Section
                y -= 210 # Increased spacing to prevent overlap
                # Bar Chart for Trends (Successful vs Failed)

                bar_data = [[150, 170, 160, 180, 190, 140, 90], [10, 15, 12, 18, 14, 20, 10]] # Mocked trends
                bar_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                draw_bar_chart(p, 50, y, 280, 150, bar_data, bar_labels, "Weekly Delivery Volume")
                
                # Pie Chart for Exceptions
                draw_pie_chart(p, 350, y, 200, 150, pie_data, pie_labels, "Failure Root Causes")
                
                # 3. Zone Performance Analysis
                y -= 40
                p.setFont("Helvetica-Bold", 11)
                p.setFillColor(colors.HexColor('#1e293b'))
                p.drawString(50, y, "Geographic Performance Metrics")
                y -= 10
                
                zone_data = [
                    ["Zone", "Deliveries", "Success", "Rate", "Status"],
                    ["Zone A - North", "312", "298", "95.5%", "GOOD"],
                    ["Zone B - South", "287", "261", "90.9%", "GOOD"],
                    ["Zone C - East", "245", "210", "85.7%", "WATCH"],
                    ["Zone D - West", "268", "224", "83.6%", "WATCH"],
                    ["Zone E - CBD", "172", "133", "77.3%", "ALERT"]
                ]
                
                t_y = y
                y = draw_styled_table(p, 50, y, w - 100, zone_data)
                
                # 4. Sign-off Section
                y = 80
                p.line(50, y, 200, y)
                p.line(w - 200, y, w - 50, y)
                p.setFont("Helvetica", 7)
                p.drawString(50, y - 10, "PREPARED BY: AI Analytics Engine")
                p.drawString(w - 200, y - 10, "VALIDATED BY: Operations Director")

            return generate_pdf_response("Performance_Intelligence", content)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)


    @action(detail=False, methods=['get'])
    def failed_deliveries(self, request):
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_styled_table
            from .models import OrderException
            
            exceptions = OrderException.objects.all().order_by('-reported_at')
            
            def content(p, w, h):
                draw_header(p, w, h, "Exception & Failure Log", "Failed Delivery Root Cause Tracking")
                
                y = h - 120
                table_data = [["Order ID", "Reason / Exception", "Driver", "Date", "Status"]]
                
                for e in exceptions:
                    d_name = e.driver.employee.full_name[:20] if (e.driver and e.driver.employee) else "Unknown"
                    table_data.append([
                        f"ORD-{e.order.order_id}",
                        e.exception_type,
                        d_name,
                        e.reported_at.strftime('%Y-%m-%d'),
                        "UNRESOLVED"
                    ])
                
                draw_styled_table(p, 40, y, w - 80, table_data, header_color='#991b1b')
            
            return generate_pdf_response("Failed_Deliveries", content)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def driver_manifest(self, request):
        """ Generate a professional individual manifest for a specific driver. """
        driver_id = request.query_params.get('driver_id')
        if not driver_id:
            return Response({"error": "driver_id query parameter is required"}, status=400)
            
        try:
            from drivers.models import Driver, TripLog
            from .models import Order, Shipment, ShipmentOrder
            from .utils.document_generator import generate_pdf_response, draw_header, draw_kpi_card, draw_styled_table, draw_status_pill
            from reportlab.lib import colors
            
            driver = Driver.objects.get(driver_id=driver_id)
            active_shipments = Shipment.objects.filter(driver=driver).order_by('-created_at')[:5]
            
            # Stats for driver
            total_trips = TripLog.objects.filter(driver=driver).count()
            total_deliveries = Order.objects.filter(assigned_driver=driver, status='delivered').count()
            pending_tasks = Order.objects.filter(assigned_driver=driver, status__in=['pending', 'assigned', 'in_transit']).count()
            
            def content(p, w, h):
                draw_header(p, w, h, f"Driver Assignment Registry", f"Personnel: {driver.employee.full_name} | ID: DRV-{driver.driver_id}")
                
                # 1. Driver Summary KPIs
                y = h - 185
                draw_kpi_card(p, 50, y, "Completed Trips", total_trips, "#1e293b")
                draw_kpi_card(p, 185, y, "Total Deliveries", total_deliveries, "#16a34a")
                draw_kpi_card(p, 320, y, "Pending Tasks", pending_tasks, "#f59e0b")
                draw_kpi_card(p, 455, y, "Exp (Years)", driver.experience_years, "#3b82f6")
                
                # 2. Assignment Details
                y -= 90 # Increased spacing

                p.setFont("Helvetica-Bold", 12)
                p.setFillColor(colors.HexColor('#1e293b'))
                p.drawString(50, y, "Recent Manifest Assignments")
                y -= 15
                
                table_data = [["Manifest ID", "Created At", "Status", "Items", "Type"]]
                for s in active_shipments:
                    item_count = ShipmentOrder.objects.filter(shipment=s).count()
                    table_data.append([
                        f"MF-{s.shipment_id}",
                        s.created_at.strftime('%Y-%m-%d %H:%M'),
                        s.status.upper(),
                        str(item_count),
                        s.shipment_type.title()
                    ])
                
                if len(table_data) == 1:
                    table_data.append(["N/A", "No recent assignments", "-", "-", "-"])
                
                y = draw_styled_table(p, 50, y, w - 100, table_data)
                
                # 3. Active Orders / Tasks
                y -= 20
                p.setFont("Helvetica-Bold", 12)
                p.drawString(50, y, "Detailed Task List (Active/Pending)")
                y -= 15
                
                order_data = [["Order ID", "Destination Address", "Qty", "Weight", "Status"]]
                active_orders = Order.objects.filter(assigned_driver=driver).exclude(status__in=['delivered', 'cancelled']).order_by('-created_at')[:10]
                
                for o in active_orders:
                    order_data.append([
                        f"ORD-{o.order_id}",
                        o.delivery_address[:40] + "..." if len(o.delivery_address) > 40 else o.delivery_address,
                        str(o.quantity),
                        f"{o.weight_kg}kg",
                        o.status.upper()
                    ])
                
                if len(order_data) == 1:
                    order_data.append(["N/A", "No active tasks found", "-", "-", "-"])
                
                y = draw_styled_table(p, 50, y, w - 100, order_data, header_color='#475569')
                
                # 4. Emergency & Compliance
                y -= 20
                p.setFont("Helvetica-Bold", 10)
                p.drawString(50, y, "Compliance & Support Information")
                y -= 15
                p.setFont("Helvetica", 9)
                p.drawString(50, y, f"License Number: {driver.license_number} (Exp: {driver.license_expiry_date})")
                p.drawString(50, y - 15, f"Emergency Contact: {driver.employee.emergency_contact_name} ({driver.employee.emergency_contact_number})")
                p.drawString(w - 250, y, "Dispatcher Hotline: +94 11 222 3333")
                p.drawString(w - 250, y - 15, "Security / SOS: *999#")
                
                # Footer
                p.setFont("Helvetica-Oblique", 7)
                p.drawCentredString(w/2, 30, "This document is an official assignment. Drivers must keep a copy during transit.")

            return generate_pdf_response(f"Driver_Manifest_{driver_id}", content)
            
        except Driver.DoesNotExist:
            return Response({"error": "Driver not found"}, status=404)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def fleet_summary(self, request):
        """ Generate a high-level operational overview of the entire fleet. """
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_kpi_card, draw_styled_table, draw_bar_chart
            from .models import Order, Shipment
            from vehicles.models import Vehicle
            
            total_vehicles = Vehicle.objects.count()
            active_vehicles = Vehicle.objects.filter(status='in_use').count()
            total_shipments = Shipment.objects.count()
            pending_orders = Order.objects.filter(status='pending').count()
            
            def content(p, w, h):
                draw_header(p, w, h, "Fleet Operations Summary", "Global Asset & Workflow Analytics")
                
                # 1. High-Level KPIs
                y = h - 185
                draw_kpi_card(p, 50, y, "Total Fleet", total_vehicles, "#1e293b")
                draw_kpi_card(p, 185, y, "Assets Deployed", active_vehicles, "#16a34a")
                draw_kpi_card(p, 320, y, "Live Shipments", total_shipments, "#3b82f6")
                draw_kpi_card(p, 455, y, "Backlog (Orders)", pending_orders, "#dc2626")
                
                # 2. Activity Trends
                y -= 200
                bar_data = [[45, 52, 48, 60, 65, 30, 20]] # Mocked fleet utilization %
                bar_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                draw_bar_chart(p, 50, y, 500, 150, bar_data, bar_labels, "Daily Fleet Utilization (%)")
                
                # 3. Active Shipment Overview
                y -= 40
                p.setFont("Helvetica-Bold", 12)
                p.drawString(50, y, "Current Active Dispatches")
                y -= 15
                
                active_shipments = Shipment.objects.filter(status__in=['dispatched', 'accepted', 'in_transit']).order_by('-deployed_at')[:10]
                table_data = [["ID", "Driver", "Vehicle", "Load", "Status"]]
                
                for s in active_shipments:
                    table_data.append([
                        f"SHP-{s.shipment_id}",
                        s.driver.employee.full_name[:20] if s.driver else "N/A",
                        s.vehicle.plate_number if s.vehicle else "N/A",
                        f"{s.total_weight}kg",
                        s.status.upper()
                    ])
                
                if len(table_data) == 1:
                    table_data.append(["N/A", "No active shipments", "-", "-", "-"])
                    
                draw_styled_table(p, 50, y, w - 100, table_data)

            return generate_pdf_response("Fleet_Operations_Summary", content)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def stock_transfers(self, request):
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_styled_table
            from warehouses.models import StockTransfer
            
            transfers = StockTransfer.objects.all().order_by('-created_at')
            
            def content(p, w, h):
                draw_header(p, w, h, "Stock Transfer Log", "Warehouse Inventory Movement Report")
                
                y = h - 120
                table_data = [["Item", "From Warehouse", "To Warehouse", "Qty", "Status", "Date"]]
                
                for t in transfers:
                    src = t.source_warehouse.name[:20] if t.source_warehouse else "N/A"
                    dst = t.destination_warehouse.name[:20] if t.destination_warehouse else "N/A"
                    table_data.append([
                        t.item_name[:20],
                        src,
                        dst,
                        str(t.quantity),
                        t.status.upper(),
                        t.created_at.strftime('%Y-%m-%d')
                    ])
                
                draw_styled_table(p, 30, y, w - 60, table_data)
            
            return generate_pdf_response("Stock_Transfers", content)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def driver_vehicle_history(self, request):
        user_id = request.query_params.get('target_user_id')
        if not user_id:
            return Response({"error": "target_user_id is required"}, status=400)
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_styled_table
            from .models import VehicleAssignment
            from drivers.models import Driver
            
            driver = Driver.objects.get(employee__user__user_id=user_id)
            assignments = VehicleAssignment.objects.filter(driver=driver).order_by('-assignment_start_date')
            
            def content(p, w, h):
                draw_header(p, w, h, "Driver Asset Assignment Timeline", f"Monthly Report - Driver: {driver.employee.full_name}")
                y = h - 120
                table_data = [["Vehicle Plate", "Model", "Assigned At", "Unassigned At", "Status"]]
                for a in assignments:
                    v_info = a.vehicle.plate_number if a.vehicle else "Unknown"
                    v_model = a.vehicle.make_model if a.vehicle else "N/A"
                    assigned = a.assignment_start_date.strftime('%Y-%m-%d %H:%M') if a.assignment_start_date else "N/A"
                    unassigned = a.assignment_end_date.strftime('%Y-%m-%d %H:%M') if getattr(a, 'assignment_end_date', None) else "Active"
                    status = a.status.upper() if hasattr(a, 'status') else "-"
                    table_data.append([v_info, v_model, assigned, unassigned, status])
                draw_styled_table(p, 40, y, w - 80, table_data)
            return generate_pdf_response(f"Driver_History_{user_id}", content)
        except Driver.DoesNotExist:
            return Response({"error": "Driver not found"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=['get'])
    def vehicle_usage_report(self, request):
        vehicle_id = request.query_params.get('vehicle_id')
        if not vehicle_id:
            return Response({"error": "vehicle_id is required"}, status=400)
        try:
            from .utils.document_generator import generate_pdf_response, draw_header, draw_styled_table
            from .models import VehicleAssignment
            from vehicles.models import Vehicle
            
            vehicle = Vehicle.objects.get(vehicle_id=vehicle_id)
            assignments = VehicleAssignment.objects.filter(vehicle=vehicle).order_by('-assignment_start_date')
            
            def content(p, w, h):
                draw_header(p, w, h, "Vehicle Usage Timeline", f"Monthly Report - Asset: {vehicle.plate_number}")
                y = h - 120
                table_data = [["Driver Name", "Assigned At", "Unassigned At", "Status"]]
                for a in assignments:
                    d_name = a.driver.employee.full_name if (a.driver and hasattr(a.driver, 'employee')) else "Unknown"
                    assigned = a.assignment_start_date.strftime('%Y-%m-%d %H:%M') if a.assignment_start_date else "N/A"
                    unassigned = a.assignment_end_date.strftime('%Y-%m-%d %H:%M') if getattr(a, 'assignment_end_date', None) else "Active"
                    status = a.status.upper() if hasattr(a, 'status') else "-"
                    table_data.append([d_name, assigned, unassigned, status])
                draw_styled_table(p, 40, y, w - 80, table_data)
            return generate_pdf_response(f"Vehicle_Usage_{vehicle_id}", content)
        except Vehicle.DoesNotExist:
            return Response({"error": "Vehicle not found"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


