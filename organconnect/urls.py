"""
URL configuration for organconnect project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from ksv import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('register/hospital/', views.register_hospital, name='register_hospital'),
    path('donor/', views.donor_register, name='donor_register'),
    path('receiver/', views.receiver_register, name='receiver_register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('hospital/suspended/', views.hospital_suspended, name='hospital_suspended'),
    path('hospital/verify/<str:user_type>/<int:pk>/', views.hospital_verify_detail, name='hospital_verify_detail'),
    path('hospital/match/', views.hospital_match_view, name='hospital_match_view'),
    path('hospital/approve-match/<int:donor_id>/<int:receiver_id>/', views.approve_match, name='approve_match'),
    path('hospital/verify-ledger/', views.verify_ledger, name='verify_ledger'),
    path('notifications/read/<int:pk>/', views.mark_notification_read, name='mark_notification_read'),
    path('matched-organs/', views.matched_organs_view, name='matched_organs'),

    
    # Secure Document Access
    path('document/download/<int:pk>/', views.download_medical_document, name='download_medical_document'),
    
    # Dedicated Admin Sub-views & Authentication
    path('admin/', views.admin_login_view, name='admin_root'),
    path('admin/login/', views.admin_login_view, name='admin_login'),
    path('admin/hospitals/', views.admin_hospital_management, name='admin_hospital_management'),
    path('admin/donors/', views.admin_donor_verification, name='admin_donor_verification'),
    path('admin/receivers/', views.admin_receiver_verification, name='admin_receiver_verification'),
    path('admin/audit-logs/', views.admin_audit_logs, name='admin_audit_logs'),
    
    # Built-in Django Admin Site
    path('django-admin/', admin.site.urls),
    
    # Admin Hospital Management Actions
    path('admin/hospital/approve/<int:pk>/', views.admin_hospital_approve, name='admin_hospital_approve'),
    path('admin/hospital/reject/<int:pk>/', views.admin_hospital_reject, name='admin_hospital_reject'),
    path('admin/hospital/toggle/<int:pk>/', views.admin_hospital_toggle_status, name='admin_hospital_toggle_status'),
    path('admin/hospital/authorize/<int:pk>/', views.admin_hospital_authorize, name='admin_hospital_authorize'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
