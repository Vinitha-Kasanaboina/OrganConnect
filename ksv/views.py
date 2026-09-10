import os
import hashlib
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponseForbidden, HttpResponseRedirect, FileResponse
from django.urls import reverse
from django.db import models
from django.contrib.auth.models import User

from .forms import UserSignUpForm, DonorForm, ReceiverForm, HospitalRegistrationForm
from .models import UserProfile, Donor, Receiver, MatchRecord, AuditLog, Notification, Hospital, MedicalDocument
from .matching_engine import run_global_matching_engine, calculate_match_score, get_automatic_matched_pairs

def is_admin(user):
    """Check if user is authenticated and is an authorized administrator."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or (hasattr(user, 'profile') and user.profile.role == 'ADMIN'):
        return True
    return False


def admin_required(view_func):
    """Decorator ensuring only authenticated Admins can access the view."""
    def _wrapped_view(request, *args, **kwargs):
        if not is_admin(request.user):
            return HttpResponseForbidden("Access Denied: Admin access required.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def home(request):
    """Public transparency landing page displaying anonymized metrics and trust logs."""
    total_donors = Donor.objects.filter(status__in=['APPROVED', 'VERIFIED', 'MATCHED']).count()
    total_receivers = Receiver.objects.filter(status__in=['APPROVED', 'VERIFIED']).count()
    total_matches = MatchRecord.objects.filter(status__in=['ACCEPTED', 'COMPLETED']).count()
    
    # Anonymized recent matches for public transparency
    recent_matches = MatchRecord.objects.filter(status__in=['ACCEPTED', 'COMPLETED']).order_by('-matched_at')[:5]
    
    return render(request, 'landing.html', {
        'total_donors': total_donors,
        'total_receivers': total_receivers,
        'total_matches': total_matches,
        'recent_matches': recent_matches
    })


def register_view(request):
    """User Sign Up View for Donors and Receivers."""
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == "POST":
        form = UserSignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            
            # Create User Profile
            profile = UserProfile.objects.create(
                user=user,
                role=form.cleaned_data['role'],
                latitude=form.cleaned_data.get('latitude'),
                longitude=form.cleaned_data.get('longitude'),
                city=form.cleaned_data.get('city', ''),
                state=form.cleaned_data.get('state', '')
            )
            
            # Log audit
            AuditLog.objects.create(
                actor=user,
                action="USER_REGISTRATION",
                details=f"Registered account with role {profile.role}."
            )
            
            login(request, user)
            
            # Redirect based on role to complete registration details
            if profile.role == 'DONOR':
                return redirect('donor_register')
            elif profile.role == 'RECEIVER':
                return redirect('receiver_register')
            else:
                return redirect('dashboard')
    else:
        form = UserSignUpForm()
        
    return render(request, 'register.html', {'form': form})


def register_hospital(request):
    """Submit a registration request for a government hospital."""
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == "POST":
        form = HospitalRegistrationForm(request.POST)
        if form.is_valid():
            # Create inactive User account
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
                is_active=False  # Must be approved by admin first
            )
            
            # Create UserProfile
            UserProfile.objects.create(
                user=user,
                role='HOSPITAL'
            )
            
            # Create Hospital Registration (Pending approval)
            hospital = form.save(commit=False)
            hospital.user = user
            hospital.status = 'PENDING'
            hospital.is_active = True
            hospital.save()
            
            # Audit log
            AuditLog.objects.create(
                actor=None,  # Unauthenticated
                action="HOSPITAL_REGISTRATION_REQUEST",
                details=f"Hospital '{hospital.name}' (Reg: {hospital.registration_number}) requested registration."
            )
            
            messages.success(request, f"Registration request for {hospital.name} submitted successfully. It will be verified by the Admin before account activation.")
            return redirect('login')
    else:
        form = HospitalRegistrationForm()
        
    return render(request, 'register_hospital.html', {'form': form})


def admin_login_view(request):
    """Dedicated secure authentication portal for the Single Master Administrator."""
    if request.user.is_authenticated:
        if is_admin(request.user):
            return redirect('dashboard')
        else:
            messages.warning(request, "Regular accounts cannot access the Master Admin Portal.")
            return redirect('dashboard')
            
    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if is_admin(user):
                login(request, user)
                AuditLog.objects.create(
                    actor=user,
                    action="ADMIN_LOGIN_SUCCESS",
                    details=f"Master Admin '{user.username}' authenticated to System Administration Console."
                )
                messages.success(request, f"Welcome Master Admin '{user.username}'. Authorized session active.")
                return redirect('dashboard')
            else:
                AuditLog.objects.create(
                    actor=user,
                    action="ADMIN_LOGIN_UNAUTHORIZED",
                    details=f"User '{user.username}' attempted admin login but is not authorized as Master Admin."
                )
                messages.error(request, "Access Denied: Account is not authorized for Master Administrator access.")
        else:
            AuditLog.objects.create(
                actor=None,
                action="ADMIN_LOGIN_FAILED",
                details=f"Failed login attempt for master admin username: '{username}'."
            )
            messages.error(request, "Invalid Master Admin credentials.")
            
    return render(request, 'admin_login.html')


def login_view(request):
    """User Login View with Role Awareness."""
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    role_param = request.GET.get('role', '').lower()
    
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            profile = getattr(user, 'profile', None)
            
            # Enforce single master admin check if attempting admin login
            if user.is_superuser or (profile and profile.role == 'ADMIN'):
                if not is_admin(user):
                    messages.error(request, "Access Denied: Unauthorized admin attempt.")
                    return redirect('login')
            
            # Check hospital status if logging in as hospital
            if profile and profile.role == 'HOSPITAL':
                h_profile = getattr(user, 'hospital_profile', None)
                if h_profile and (h_profile.status != 'APPROVED' or not h_profile.is_active):
                    login(request, user)
                    return redirect('hospital_suspended')
            
            login(request, user)
            return redirect('dashboard')
            
        messages.error(request, "Invalid username or password.")
        
    return render(request, 'login.html', {'selected_role': role_param})



def logout_view(request):
    """User Logout View."""
    logout(request)
    return redirect('login')


@login_required
def hospital_suspended(request):
    """Page displayed to pending/suspended/rejected hospital accounts."""
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != 'HOSPITAL':
        return redirect('dashboard')
        
    h_profile = getattr(request.user, 'hospital_profile', None)
    if h_profile and h_profile.status == 'APPROVED' and h_profile.is_active:
        return redirect('dashboard')
        
    return render(request, 'hospital_suspended.html', {'hospital': h_profile})


@login_required
def donor_register(request):
    """Donor Profile Creation/Modification Form with Document Uploads."""
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != 'DONOR':
        return HttpResponseForbidden("Only Donors can access this page.")
        
    donor = getattr(request.user, 'donor_profile', None)
    
    if request.method == "POST":
        form = DonorForm(request.POST, request.FILES, instance=donor)
        if form.is_valid():
            donor = form.save(commit=False)
            donor.user = request.user
            donor.save()
            
            # Process uploaded document files
            file_fields = [
                ('health_report', 'HEALTH_REPORT', 'Health Report / Medical History'),
                ('blood_test_report', 'BLOOD_TEST', 'Blood Test Report'),
                ('hla_report', 'HLA_REPORT', 'HLA Tissue Typing Report'),
                ('fitness_certificate', 'FITNESS_CERTIFICATE', 'Organ Fitness Certificate'),
                ('supporting_document', 'OTHER', 'Supporting Document'),
            ]
            
            for field_name, doc_type, default_title in file_fields:
                file_obj = form.cleaned_data.get(field_name)
                if file_obj:
                    MedicalDocument.objects.create(
                        donor=donor,
                        document_type=doc_type,
                        file=file_obj,
                        title=file_obj.name or default_title
                    )
            
            AuditLog.objects.create(
                actor=request.user,
                action="DONOR_PROFILE_UPDATE",
                details=f"Updated donor profile and uploaded medical documents for ID: {donor.anonymous_id}."
            )
            
            messages.success(request, "Donor profile and medical documents submitted successfully for hospital verification.")
            return redirect('dashboard')
    else:
        form = DonorForm(instance=donor)
        if donor:
            form.fields['medical_history'].initial = donor.medical_records
            
    documents = donor.documents.all() if donor else []
    return render(request, 'donor_form.html', {'form': form, 'donor': donor, 'documents': documents})


@login_required
def receiver_register(request):
    """Receiver Profile Creation/Modification Form with Document Uploads."""
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != 'RECEIVER':
        return HttpResponseForbidden("Only Receivers can access this page.")
        
    receiver = getattr(request.user, 'receiver_profile', None)
    
    if request.method == "POST":
        form = ReceiverForm(request.POST, request.FILES, instance=receiver)
        if form.is_valid():
            receiver = form.save(commit=False)
            receiver.user = request.user
            receiver.save()
            
            # Process uploaded document files
            file_fields = [
                ('doctor_diagnosis', 'DIAGNOSIS', "Doctor's Diagnosis Report"),
                ('transplant_recommendation', 'TRANSPLANT_REC', 'Transplant Recommendation Letter'),
                ('lab_reports', 'LAB_REPORT', 'Laboratory Test Reports'),
                ('medical_history_doc', 'HEALTH_REPORT', 'Medical History Document'),
                ('hla_report', 'HLA_REPORT', 'HLA Tissue Typing Report'),
                ('supporting_document', 'OTHER', 'Supporting Document'),
            ]
            
            for field_name, doc_type, default_title in file_fields:
                file_obj = form.cleaned_data.get(field_name)
                if file_obj:
                    MedicalDocument.objects.create(
                        receiver=receiver,
                        document_type=doc_type,
                        file=file_obj,
                        title=file_obj.name or default_title
                    )
            
            AuditLog.objects.create(
                actor=request.user,
                action="RECEIVER_PROFILE_UPDATE",
                details=f"Updated receiver profile and uploaded medical documents for ID: {receiver.anonymous_id}."
            )
            
            messages.success(request, "Receiver profile and medical documents submitted successfully for hospital verification.")
            return redirect('dashboard')
    else:
        form = ReceiverForm(instance=receiver)
        if receiver:
            form.fields['medical_history'].initial = receiver.medical_records
            
    documents = receiver.documents.all() if receiver else []
    return render(request, 'receiver_form.html', {'form': form, 'receiver': receiver, 'documents': documents})


@login_required
def download_medical_document(request, pk):
    """Securely serve medical documents to authorized Admins, assigned Hospitals, or the file owner."""
    doc = get_object_or_404(MedicalDocument, pk=pk)
    user = request.user
    
    authorized = False
    if is_admin(user):
        authorized = True
    elif doc.donor and doc.donor.user == user:
        authorized = True
    elif doc.receiver and doc.receiver.user == user:
        authorized = True
    elif hasattr(user, 'profile') and user.profile.role == 'HOSPITAL':
        h_profile = getattr(user, 'hospital_profile', None)
        if h_profile and h_profile.status == 'APPROVED' and h_profile.is_active:
            patient_hospital = doc.donor.hospital if doc.donor else (doc.receiver.hospital if doc.receiver else None)
            accessible_hospitals = [h_profile] + list(h_profile.authorized_hospitals.all())
            if patient_hospital in accessible_hospitals:
                authorized = True
                
    if not authorized:
        return HttpResponseForbidden("Access Denied: You are not authorized to view or download this medical document.")
        
    return FileResponse(doc.file.open('rb'), filename=doc.title or os.path.basename(doc.file.name))


@login_required
def dashboard(request):
    """Central Dashboard Router routing users to Donor, Receiver, Hospital, or Admin views."""
    auto_matched_pairs = get_automatic_matched_pairs()

    if is_admin(request.user):
        pending_hospitals = Hospital.objects.filter(status='PENDING')
        approved_hospitals = Hospital.objects.filter(status='APPROVED')
        rejected_hospitals = Hospital.objects.filter(status='REJECTED')
        
        verified_donors = Donor.objects.filter(status__in=['APPROVED', 'VERIFIED'])
        pending_donors = Donor.objects.filter(status='PENDING')
        verified_receivers = Receiver.objects.filter(status__in=['APPROVED', 'VERIFIED'])
        pending_receivers = Receiver.objects.filter(status='PENDING')
        
        matches = MatchRecord.objects.all().order_by('-matched_at')
        audit_logs = AuditLog.objects.all().order_by('-timestamp')[:50]
        
        return render(request, 'dashboard.html', {
            'role': 'ADMIN',
            'pending_hospitals': pending_hospitals,
            'approved_hospitals': approved_hospitals,
            'rejected_hospitals': rejected_hospitals,
            'pending_donors': pending_donors,
            'verified_donors': verified_donors,
            'pending_receivers': pending_receivers,
            'verified_receivers': verified_receivers,
            'matches': matches,
            'auto_matched_pairs': auto_matched_pairs,
            'audit_logs': audit_logs
        })
        
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return redirect('register')
        
    notifications = request.user.notifications.filter(is_read=False).order_by('-created_at')
    
    if profile.role == 'DONOR':
        donor = getattr(request.user, 'donor_profile', None)
        if not donor:
            return redirect('donor_register')
            
        matches = MatchRecord.objects.filter(donor=donor, status='ACCEPTED')
        donor_auto_matches = [m for m in auto_matched_pairs if m['donor'].id == donor.id]
        documents = donor.documents.all() if donor else []
        return render(request, 'dashboard.html', {
            'profile': profile,
            'role': 'DONOR',
            'donor': donor,
            'matches': matches,
            'auto_matched_pairs': donor_auto_matches if donor_auto_matches else auto_matched_pairs,
            'documents': documents,
            'notifications': notifications
        })
        
    elif profile.role == 'RECEIVER':
        receiver = getattr(request.user, 'receiver_profile', None)
        if not receiver:
            return redirect('receiver_register')
            
        matches = MatchRecord.objects.filter(receiver=receiver, status='ACCEPTED')
        receiver_auto_matches = [m for m in auto_matched_pairs if m['receiver'].id == receiver.id]
        documents = receiver.documents.all() if receiver else []
        return render(request, 'dashboard.html', {
            'profile': profile,
            'role': 'RECEIVER',
            'receiver': receiver,
            'matches': matches,
            'auto_matched_pairs': receiver_auto_matches if receiver_auto_matches else auto_matched_pairs,
            'documents': documents,
            'notifications': notifications
        })
        
    elif profile.role == 'HOSPITAL':
        h_profile = getattr(request.user, 'hospital_profile', None)
        if not h_profile or h_profile.status != 'APPROVED' or not h_profile.is_active:
            return redirect('hospital_suspended')
            
        # Access Isolation: Restrict data viewing to designated hospital pool
        accessible_hospitals = [h_profile] + list(h_profile.authorized_hospitals.all())
        
        pending_donors = Donor.objects.filter(status='PENDING', hospital__in=accessible_hospitals)
        pending_receivers = Receiver.objects.filter(status='PENDING', hospital__in=accessible_hospitals)
        
        verified_donors = Donor.objects.filter(status__in=['APPROVED', 'VERIFIED'], hospital__in=accessible_hospitals)
        verified_receivers = Receiver.objects.filter(status__in=['APPROVED', 'VERIFIED'], hospital__in=accessible_hospitals)
        
        matches = MatchRecord.objects.filter(
            models.Q(donor__hospital__in=accessible_hospitals) | 
            models.Q(receiver__hospital__in=accessible_hospitals)
        ).distinct().order_by('-matched_at')
        
        hospital_auto_matches = [
            m for m in auto_matched_pairs
            if m['donor_hospital'] in accessible_hospitals or m['receiver_hospital'] in accessible_hospitals or m['hospital'] == "Unassigned"
        ]
        
        audit_logs = AuditLog.objects.all().order_by('-timestamp')[:50]
        
        return render(request, 'dashboard.html', {
            'profile': profile,
            'role': 'HOSPITAL',
            'hospital': h_profile,
            'pending_donors': pending_donors,
            'pending_receivers': pending_receivers,
            'verified_donors': verified_donors,
            'verified_receivers': verified_receivers,
            'matches': matches,
            'auto_matched_pairs': hospital_auto_matches,
            'audit_logs': audit_logs,
            'notifications': notifications
        })
        
    return HttpResponseForbidden("Access Denied.")


@login_required
def matched_organs_view(request):
    """Standalone page displaying all automatically matched donor and receiver pairs."""
    matched_pairs = get_automatic_matched_pairs()
    return render(request, 'matched_organs.html', {
        'matched_pairs': matched_pairs
    })



# Dedicated Admin Dashboard Sub-views
@login_required
@admin_required
def admin_hospital_management(request):
    """Admin view for Hospital Management."""
    pending_hospitals = Hospital.objects.filter(status='PENDING')
    approved_hospitals = Hospital.objects.filter(status='APPROVED')
    rejected_hospitals = Hospital.objects.filter(status='REJECTED')
    return render(request, 'admin_hospitals.html', {
        'pending_hospitals': pending_hospitals,
        'approved_hospitals': approved_hospitals,
        'rejected_hospitals': rejected_hospitals,
    })


@login_required
@admin_required
def admin_donor_verification(request):
    """Admin view for Donor Verification Requests."""
    pending_donors = Donor.objects.filter(status='PENDING')
    verified_donors = Donor.objects.filter(status__in=['APPROVED', 'VERIFIED'])
    rejected_donors = Donor.objects.filter(status='REJECTED')
    return render(request, 'admin_donors.html', {
        'pending_donors': pending_donors,
        'verified_donors': verified_donors,
        'rejected_donors': rejected_donors,
    })


@login_required
@admin_required
def admin_receiver_verification(request):
    """Admin view for Receiver Verification Requests."""
    pending_receivers = Receiver.objects.filter(status='PENDING')
    verified_receivers = Receiver.objects.filter(status__in=['APPROVED', 'VERIFIED'])
    rejected_receivers = Receiver.objects.filter(status='REJECTED')
    return render(request, 'admin_receivers.html', {
        'pending_receivers': pending_receivers,
        'verified_receivers': verified_receivers,
        'rejected_receivers': rejected_receivers,
    })


@login_required
@admin_required
def admin_audit_logs(request):
    """Admin view for Cryptographic Audit Logs."""
    audit_logs = AuditLog.objects.all().order_by('-timestamp')
    return render(request, 'admin_audit_logs.html', {
        'audit_logs': audit_logs,
    })


@login_required
def hospital_verify_detail(request, user_type, pk):
    """Review and verify a donor or receiver documents. Access restricted to authorized hospitals/admins."""
    if is_admin(request.user):
        is_hospital_officer = False
    else:
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role != 'HOSPITAL':
            return HttpResponseForbidden("Access Denied.")
            
        h_profile = getattr(request.user, 'hospital_profile', None)
        if not h_profile or h_profile.status != 'APPROVED' or not h_profile.is_active:
            return redirect('hospital_suspended')
            
        is_hospital_officer = True
        
    obj = None
    if user_type == 'donor':
        obj = get_object_or_404(Donor, pk=pk)
    elif user_type == 'receiver':
        obj = get_object_or_404(Receiver, pk=pk)
    else:
        return redirect('dashboard')
        
    # Isolation Check
    if not is_admin(request.user):
        accessible_hospitals = [h_profile] + list(h_profile.authorized_hospitals.all())
        if obj.hospital not in accessible_hospitals:
            return HttpResponseForbidden("Access Denied. You are not authorized to view patients from this hospital.")
            
    if request.method == "POST" and is_hospital_officer:
        action = request.POST.get('action')
        urgency = request.POST.get('urgency')
        notes = request.POST.get('notes', '').strip()
        
        if action == 'approve':
            obj.status = 'APPROVED'
            obj.verified_by = request.user
            obj.verified_at = timezone.now()
            obj.verification_remarks = notes
            
            if user_type == 'receiver' and urgency:
                obj.medical_urgency = urgency
                
            obj.save()
            
            AuditLog.objects.create(
                actor=request.user,
                action=f"{user_type.upper()}_VERIFIED",
                details=f"Approved {obj.anonymous_id} (Hospital: {obj.hospital.name if obj.hospital else 'General'}). Remarks: {notes}"
            )
            
            if obj.user:
                Notification.objects.create(
                    user=obj.user,
                    message=f"Your medical documents have been verified and APPROVED by {obj.hospital.name if obj.hospital else 'Government Hospital'}. Remarks: {notes}"
                )
                
            messages.success(request, f"{obj.anonymous_id} verified and APPROVED successfully.")
            
        elif action == 'reject':
            obj.status = 'REJECTED'
            obj.verified_by = request.user
            obj.verified_at = timezone.now()
            obj.verification_remarks = notes
            obj.save()
            
            AuditLog.objects.create(
                actor=request.user,
                action=f"{user_type.upper()}_REJECTED",
                details=f"Rejected {obj.anonymous_id} (Hospital: {obj.hospital.name if obj.hospital else 'General'}). Remarks: {notes}"
            )
            
            if obj.user:
                Notification.objects.create(
                    user=obj.user,
                    message=f"Your profile verification was REJECTED by Government Hospital. Remarks: {notes}"
                )
                
            messages.warning(request, f"{obj.anonymous_id} has been REJECTED.")
            
        return redirect('dashboard')
        
    decrypted_records = obj.medical_records
    documents = obj.documents.all()
    
    return render(request, 'hospital_verify.html', {
        'applicant': obj,
        'user_type': user_type,
        'decrypted_records': decrypted_records,
        'documents': documents,
        'is_hospital_officer': is_hospital_officer,
    })


@login_required
def hospital_match_view(request):
    """View and run the AI matching engine to propose matching recommendations."""
    if is_admin(request.user):
        recommendations = run_global_matching_engine()
    else:
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role != 'HOSPITAL':
            return HttpResponseForbidden("Access Denied.")
            
        h_profile = getattr(request.user, 'hospital_profile', None)
        if not h_profile or h_profile.status != 'APPROVED' or not h_profile.is_active:
            return redirect('hospital_suspended')
            
        recommendations = run_global_matching_engine()
        
        accessible_hospitals = [h_profile] + list(h_profile.authorized_hospitals.all())
        recommendations = [
            rec for rec in recommendations
            if rec['donor'].hospital in accessible_hospitals or rec['receiver'].hospital in accessible_hospitals
        ]
        
    return render(request, 'hospital_match.html', {
        'recommendations': recommendations
    })


@login_required
def approve_match(request, donor_id, receiver_id):
    """Approve a proposed match, notifying both parties and writing audit records."""
    if is_admin(request.user):
        return HttpResponseForbidden("Only Hospital Officials can approve matches.")
        
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != 'HOSPITAL':
        return HttpResponseForbidden("Access Denied.")
        
    h_profile = getattr(request.user, 'hospital_profile', None)
    if not h_profile or h_profile.status != 'APPROVED' or not h_profile.is_active:
        return redirect('hospital_suspended')
        
    donor = get_object_or_404(Donor, pk=donor_id)
    receiver = get_object_or_404(Receiver, pk=receiver_id)
    
    accessible_hospitals = [h_profile] + list(h_profile.authorized_hospitals.all())
    if donor.hospital not in accessible_hospitals and receiver.hospital not in accessible_hospitals:
        return HttpResponseForbidden("You are not authorized to approve matches for these patient records.")
        
    if donor.status not in ['APPROVED', 'VERIFIED'] or receiver.status not in ['APPROVED', 'VERIFIED']:
        messages.error(request, "Both donor and receiver must be in APPROVED status to match.")
        return redirect('hospital_match_view')
        
    match_info = calculate_match_score(donor, receiver)
    rationale = "\n".join(match_info['reasons'])
    
    match_rec = MatchRecord.objects.create(
        donor=donor,
        receiver=receiver,
        compatibility_score=match_info['score'],
        matching_rationale=rationale,
        status='ACCEPTED',
        verified_by=request.user
    )
    
    donor.status = 'MATCHED'
    receiver.status = 'MATCHED'
    donor.save()
    receiver.save()
    
    AuditLog.objects.create(
        actor=request.user,
        action="MATCH_APPROVED",
        details=f"Approved match: {donor.anonymous_id} -> {receiver.anonymous_id} (Score: {match_info['score']}%)."
    )
    
    if donor.user:
        Notification.objects.create(
            user=donor.user,
            message=f"A matching receiver has been found! Receiver ID: {receiver.anonymous_id} ({receiver.blood_group} blood, {receiver.organ}). Contact government hospital for transplant coordination."
        )
        
    if receiver.user:
        Notification.objects.create(
            user=receiver.user,
            message=f"Congratulations! A matching organ donor has been found: Donor ID: {donor.anonymous_id} ({donor.blood_group} blood, {donor.organ}). Please contact the government hospital immediately."
        )
        
    messages.success(request, f"Match approved between Donor {donor.anonymous_id} and Receiver {receiver.anonymous_id} successfully!")
    return redirect('dashboard')


@login_required
def mark_notification_read(request, pk):
    """Mark notification as read."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', reverse('dashboard')))


@login_required
def verify_ledger(request):
    """Cryptographic audit chain verification view for Government Officials."""
    logs = AuditLog.objects.order_by('id')
    integrity_ok = True
    tampered_logs = []
    expected_prev = "0" * 64
    
    for log in logs:
        t_str = log.timestamp.isoformat() if log.timestamp else "new-log"
        actor_id = str(log.actor.id) if log.actor else "system"
        raw_data = f"{actor_id}{log.action}{log.details}{t_str}{log.previous_hash}"
        computed_hash = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
        
        if log.previous_hash != expected_prev:
            integrity_ok = False
            tampered_logs.append(f"Log #{log.id} [Chain Broken: expected prev_hash '{expected_prev[:8]}...', got '{log.previous_hash[:8]}...']")
        if log.hash != computed_hash:
            integrity_ok = False
            tampered_logs.append(f"Log #{log.id} [Tampered Content: expected hash '{computed_hash[:8]}...', got '{log.hash[:8]}...']")
            
        expected_prev = log.hash
        
    if integrity_ok:
        messages.success(request, "🛡️ Ledger Chain Verification Successful: Cryptographic audit history is authentic and untampered.")
    else:
        messages.error(request, f"⚠️ Ledger Chain Verification FAILED! Tampering detected in the following blocks: {', '.join(tampered_logs)}")
        
    return redirect(request.META.get('HTTP_REFERER', reverse('dashboard')))


# ADMIN HOSPITAL MANAGEMENT ACTIONS
@login_required
@admin_required
def admin_hospital_approve(request, pk):
    """Approve a pending hospital registration request."""
    hospital = get_object_or_404(Hospital, pk=pk)
    if hospital.status == 'PENDING':
        hospital.status = 'APPROVED'
        hospital.is_active = True
        hospital.save()
        
        if hospital.user:
            hospital.user.is_active = True
            hospital.user.save()
            
        AuditLog.objects.create(
            actor=request.user,
            action="HOSPITAL_APPROVE",
            details=f"Approved hospital: '{hospital.name}' (Reg: {hospital.registration_number})."
        )
        
        messages.success(request, f"Hospital {hospital.name} registration approved and login account activated.")
    else:
        messages.warning(request, f"Hospital {hospital.name} is not in PENDING state.")
        
    return redirect(request.META.get('HTTP_REFERER', reverse('dashboard')))


@login_required
@admin_required
def admin_hospital_reject(request, pk):
    """Reject a pending hospital registration request."""
    hospital = get_object_or_404(Hospital, pk=pk)
    if hospital.status == 'PENDING':
        hospital.status = 'REJECTED'
        hospital.is_active = False
        hospital.save()
        
        if hospital.user:
            hospital.user.is_active = False
            hospital.user.save()
            
        AuditLog.objects.create(
            actor=request.user,
            action="HOSPITAL_REJECT",
            details=f"Rejected hospital request: '{hospital.name}' (Reg: {hospital.registration_number})."
        )
        
        messages.warning(request, f"Hospital {hospital.name} registration request rejected.")
    else:
        messages.warning(request, f"Hospital {hospital.name} is not in PENDING state.")
        
    return redirect(request.META.get('HTTP_REFERER', reverse('dashboard')))


@login_required
@admin_required
def admin_hospital_toggle_status(request, pk):
    """Suspend or re-activate an approved hospital's access."""
    hospital = get_object_or_404(Hospital, pk=pk)
    if hospital.status == 'APPROVED':
        hospital.is_active = not hospital.is_active
        hospital.save()
        
        if hospital.user:
            hospital.user.is_active = hospital.is_active
            hospital.user.save()
            
        status_word = "Activated" if hospital.is_active else "Suspended/Deactivated"
        action_code = "HOSPITAL_ACTIVATE" if hospital.is_active else "HOSPITAL_SUSPEND"
        
        AuditLog.objects.create(
            actor=request.user,
            action=action_code,
            details=f"{status_word} hospital access: '{hospital.name}'."
        )
        
        messages.success(request, f"Hospital {hospital.name} access status changed to: {status_word}.")
    else:
        messages.error(request, f"Hospital {hospital.name} must be approved first.")
        
    return redirect(request.META.get('HTTP_REFERER', reverse('dashboard')))


@login_required
@admin_required
def admin_hospital_authorize(request, pk):
    """Authorize a hospital to view patient lists from other hospitals."""
    hospital = get_object_or_404(Hospital, pk=pk)
    other_hospitals = Hospital.objects.filter(status='APPROVED').exclude(pk=hospital.pk)
    
    if request.method == "POST":
        selected_ids = request.POST.getlist('authorized_hospitals')
        selected_hospitals = Hospital.objects.filter(pk__in=selected_ids)
        
        hospital.authorized_hospitals.set(selected_hospitals)
        
        AuditLog.objects.create(
            actor=request.user,
            action="HOSPITAL_GRANT_ACCESS",
            details=f"Granted '{hospital.name}' permission to view data from: {[h.name for h in selected_hospitals]}."
        )
        
        messages.success(request, f"Access authorizations updated for {hospital.name}.")
        return redirect('dashboard')
        
    return render(request, 'admin_authorize_hospital.html', {
        'hospital': hospital,
        'other_hospitals': other_hospitals,
    })