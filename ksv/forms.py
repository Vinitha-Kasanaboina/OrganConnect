from django import forms
from django.contrib.auth.models import User
from .models import Donor, Receiver, UserProfile, Hospital

class UserSignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    
    # Filter public signup to only allow Donors and Receivers
    role = forms.ChoiceField(
        choices=[('DONOR', 'Donor'), ('RECEIVER', 'Receiver')], 
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    latitude = forms.FloatField(required=False, widget=forms.HiddenInput())
    longitude = forms.FloatField(required=False, widget=forms.HiddenInput())
    city = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'City'}))
    state = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'State'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Username'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email Address'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data


class HospitalRegistrationForm(forms.ModelForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Desired Username'}),
        label="Account Username"
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Desired Email Address'}),
        label="Account Email"
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Password'}),
        label="Account Password"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Confirm Password'}),
        label="Confirm Password"
    )

    class Meta:
        model = Hospital
        fields = ['name', 'registration_number', 'address', 'contact_info', 'authorized_officer']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Official Hospital Name'}),
            'registration_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Govt. Registration Number'}),
            'address': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Hospital Address'}),
            'contact_info': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Contact Number/Email'}),
            'authorized_officer': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Authorized Medical Officer'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already registered.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data


class DonorForm(forms.ModelForm):
    gender = forms.ChoiceField(
        choices=Donor.GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-input'}),
        label="Gender"
    )
    contact_info = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Phone / Email / Address'}),
        label="Contact Information",
        required=True
    )
    hospital = forms.ModelChoiceField(
        queryset=Hospital.objects.filter(status='APPROVED', is_active=True),
        widget=forms.Select(attrs={'class': 'form-input'}),
        label="Designated Government Hospital",
        required=True
    )
    medical_history = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Optional brief health overview or notes...'}),
        label="Additional Health Notes",
        required=False
    )
    
    # Document Upload Fields
    health_report = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="Health / Medical Report",
        required=False
    )
    blood_test_report = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="Blood Test Report",
        required=False
    )
    hla_report = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="HLA Tissue Typing Report (If Available)",
        required=False
    )
    fitness_certificate = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="Organ Fitness Certificate",
        required=False
    )
    supporting_document = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="Other Supporting Documents",
        required=False
    )

    class Meta:
        model = Donor
        fields = ['name', 'age', 'gender', 'blood_group', 'organ', 'contact_info', 'weight', 'bp', 'hla_typing', 'hospital']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full Name'}),
            'age': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Age'}),
            'blood_group': forms.Select(attrs={'class': 'form-input'}),
            'organ': forms.Select(attrs={'class': 'form-input'}),
            'weight': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Weight in kg (Default: 60)'}),
            'bp': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Blood Pressure (e.g. 120/80)'}),
            'hla_typing': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. A*02:01, B*27:05'}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('medical_history'):
            instance.medical_records = self.cleaned_data['medical_history']
        if commit:
            instance.save()
        return instance


class ReceiverForm(forms.ModelForm):
    gender = forms.ChoiceField(
        choices=Receiver.GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-input'}),
        label="Gender"
    )
    contact_info = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Phone / Email / Address'}),
        label="Contact Information",
        required=True
    )
    hospital = forms.ModelChoiceField(
        queryset=Hospital.objects.filter(status='APPROVED', is_active=True),
        widget=forms.Select(attrs={'class': 'form-input'}),
        label="Designated Government Hospital",
        required=True
    )
    medical_history = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Optional summary of diagnosis or recipient condition notes...'}),
        label="Additional Health Notes",
        required=False
    )
    
    # Document Upload Fields
    doctor_diagnosis = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="Doctor's Diagnosis Report",
        required=False
    )
    transplant_recommendation = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="Transplant Recommendation Letter",
        required=False
    )
    lab_reports = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="Laboratory Test Reports",
        required=False
    )
    medical_history_doc = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="Complete Medical History Document",
        required=False
    )
    hla_report = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="HLA Tissue Typing Report (If Available)",
        required=False
    )
    supporting_document = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
        label="Other Supporting Documents",
        required=False
    )

    class Meta:
        model = Receiver
        fields = ['name', 'age', 'gender', 'blood_group', 'organ', 'contact_info', 'weight', 'bp', 'hla_typing', 'medical_urgency', 'hospital']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full Name'}),
            'age': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Age'}),
            'blood_group': forms.Select(attrs={'class': 'form-input'}),
            'organ': forms.Select(attrs={'class': 'form-input'}),
            'weight': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Weight in kg (Default: 60)'}),
            'bp': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Blood Pressure (e.g. 120/80)'}),
            'hla_typing': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. A*02:01, B*27:05'}),
            'medical_urgency': forms.Select(attrs={'class': 'form-input'}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('medical_history'):
            instance.medical_records = self.cleaned_data['medical_history']
        if commit:
            instance.save()
        return instance