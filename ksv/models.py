import uuid
import hashlib
from django.db import models
from django.conf import settings
from django.utils import timezone

class UserProfile(models.Model):
    ROLES = [
        ('DONOR', 'Donor'),
        ('RECEIVER', 'Receiver'),
        ('HOSPITAL', 'Government Hospital Official'),
        ('ADMIN', 'Admin'),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLES)
    
    # Location coordinates for Google Maps & Leaflet
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    # Regional fields for location matching/fallback
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Hospital(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    name = models.CharField(max_length=200)
    registration_number = models.CharField(max_length=100, unique=True)
    address = models.TextField()
    contact_info = models.CharField(max_length=100)
    authorized_officer = models.CharField(max_length=100)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='hospital_profile')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    is_active = models.BooleanField(default=True)
    
    # Permission: Admin can authorize this hospital to view data from other hospitals
    authorized_hospitals = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='authorized_by')

    def __str__(self):
        return f"{self.name} ({self.registration_number})"


class Donor(models.Model):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]

    BLOOD_GROUPS = [
        ('A+', 'A+'),
        ('A-', 'A-'),
        ('B+', 'B+'),
        ('B-', 'B-'),
        ('AB+', 'AB+'),
        ('AB-', 'AB-'),
        ('O+', 'O+'),
        ('O-', 'O-'),
    ]

    ORGANS = [
        ('Kidney', 'Kidney'),
        ('Liver', 'Liver'),
        ('Heart', 'Heart'),
        ('Lung', 'Lung'),
        ('Pancreas', 'Pancreas'),
        ('Cornea', 'Cornea'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending Verification'),
        ('APPROVED', 'Approved'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
        ('MATCHED', 'Matched'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='donor_profile', null=True, blank=True)
    hospital = models.ForeignKey(Hospital, on_delete=models.SET_NULL, null=True, blank=True, related_name='donors')
    anonymous_id = models.CharField(max_length=30, unique=True, blank=True)
    name = models.CharField(max_length=100)
    age = models.IntegerField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='Male')
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUPS)
    organ = models.CharField(max_length=20, choices=ORGANS)
    weight = models.FloatField(default=60.0)
    bp = models.CharField(max_length=20, default='120/80')
    contact_info = models.CharField(max_length=150, blank=True)
    
    # AI compatibility / Medical details
    hla_typing = models.CharField(max_length=50, blank=True, help_text="HLA typing code (e.g. A*02:01, B*27:05, DRB1*04:01)")
    encrypted_medical_records = models.TextField(blank=True, help_text="Encrypted medical examination details")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    verification_remarks = models.TextField(blank=True, help_text="Hospital review comments/notes")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_donors')
    verified_at = models.DateTimeField(null=True, blank=True)

    @property
    def medical_records(self):
        from .security import decrypt_data
        return decrypt_data(self.encrypted_medical_records)

    @medical_records.setter
    def medical_records(self, value):
        from .security import encrypt_data
        self.encrypted_medical_records = encrypt_data(value)

    def save(self, *args, **kwargs):
        if not self.anonymous_id:
            # Generate static secure anonymous identifier for blind matching
            self.anonymous_id = f"OC-D-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Donor: {self.anonymous_id} ({self.organ}, {self.blood_group})"


class Receiver(models.Model):
    GENDER_CHOICES = Donor.GENDER_CHOICES
    BLOOD_GROUPS = Donor.BLOOD_GROUPS
    ORGANS = Donor.ORGANS
    STATUS_CHOICES = Donor.STATUS_CHOICES

    URGENCY_CHOICES = [
        ('LOW', 'Low Urgency'),
        ('MEDIUM', 'Medium Urgency'),
        ('HIGH', 'High Urgency'),
        ('CRITICAL', 'Critical Urgency'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='receiver_profile', null=True, blank=True)
    hospital = models.ForeignKey(Hospital, on_delete=models.SET_NULL, null=True, blank=True, related_name='receivers')
    anonymous_id = models.CharField(max_length=30, unique=True, blank=True)
    name = models.CharField(max_length=100)
    age = models.IntegerField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='Male')
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUPS)
    organ = models.CharField(max_length=20, choices=ORGANS)
    weight = models.FloatField(default=60.0)
    bp = models.CharField(max_length=20, default='120/80')
    contact_info = models.CharField(max_length=150, blank=True)
    
    # AI compatibility / Medical details
    hla_typing = models.CharField(max_length=50, blank=True, help_text="HLA typing code (e.g. A*02:01, B*27:05, DRB1*04:01)")
    encrypted_medical_records = models.TextField(blank=True, help_text="Encrypted receiver medical files")
    
    medical_urgency = models.CharField(max_length=20, choices=URGENCY_CHOICES, default='LOW')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    verification_remarks = models.TextField(blank=True, help_text="Hospital review comments/notes")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_receivers')
    verified_at = models.DateTimeField(null=True, blank=True)

    @property
    def medical_records(self):
        from .security import decrypt_data
        return decrypt_data(self.encrypted_medical_records)

    @medical_records.setter
    def medical_records(self, value):
        from .security import encrypt_data
        self.encrypted_medical_records = encrypt_data(value)

    def save(self, *args, **kwargs):
        if not self.anonymous_id:
            # Generate static secure anonymous identifier for blind matching
            self.anonymous_id = f"OC-R-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Receiver: {self.anonymous_id} ({self.organ}, {self.blood_group}, Urgency: {self.medical_urgency})"


class MedicalDocument(models.Model):
    DOCUMENT_TYPES = [
        ('HEALTH_REPORT', 'Health Report / Medical History'),
        ('BLOOD_TEST', 'Blood Test Report'),
        ('HLA_REPORT', 'HLA Tissue Typing Report'),
        ('FITNESS_CERTIFICATE', 'Organ Fitness Certificate'),
        ('DIAGNOSIS', 'Doctor Diagnosis'),
        ('TRANSPLANT_REC', 'Transplant Recommendation'),
        ('LAB_REPORT', 'Laboratory Report'),
        ('OTHER', 'Other Supporting Document'),
    ]
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    receiver = models.ForeignKey(Receiver, on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    file = models.FileField(upload_to='medical_documents/')
    title = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        target = f"Donor {self.donor.anonymous_id}" if self.donor else (f"Receiver {self.receiver.anonymous_id}" if self.receiver else "Unassigned")
        return f"{self.get_document_type_display()} - {target}"



class MatchRecord(models.Model):
    STATUS_CHOICES = [
        ('PROPOSED', 'Proposed Match'),
        ('ACCEPTED', 'Accepted/Approved'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name='matches')
    receiver = models.ForeignKey(Receiver, on_delete=models.CASCADE, related_name='matches')
    compatibility_score = models.FloatField()
    matched_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROPOSED')
    matching_rationale = models.TextField(blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_matches')

    def __str__(self):
        return f"Match: {self.donor.anonymous_id} -> {self.receiver.anonymous_id} (Score: {self.compatibility_score}%)"


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    
    timestamp = models.DateTimeField(default=timezone.now)
    
    # Cryptographic Chain Ledger
    hash = models.CharField(max_length=64, blank=True)
    previous_hash = models.CharField(max_length=64, blank=True)

    def save(self, *args, **kwargs):
        if not self.timestamp:
            self.timestamp = timezone.now()

        # Establish link to the previous audit log hash (blockchain-style ledger link)
        if not self.previous_hash:
            last_log = AuditLog.objects.order_by('-id').first()
            if last_log:
                self.previous_hash = last_log.hash
            else:
                self.previous_hash = "0" * 64
                
        t_str = self.timestamp.isoformat()
        actor_id = str(self.actor.id) if self.actor else "system"
        
        raw_data = f"{actor_id}{self.action}{self.details}{t_str}{self.previous_hash}"
        self.hash = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"AuditLog: {self.action} by {self.actor} at {self.timestamp}"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user.username} (Read: {self.is_read})"


# Signals for Automatic Organ Matching Synchronization
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Donor)
@receiver(post_save, sender=Receiver)
def trigger_auto_organ_matching(sender, instance, created, **kwargs):
    """Automatically update organ matches whenever a donor or receiver is added/updated."""
    try:
        from .matching_engine import sync_automatic_matches
        sync_automatic_matches()
    except Exception:
        pass