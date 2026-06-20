from django.urls import path

from . import views


urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("verify/", views.verify_payment, name="verify_payment"),
    path("success/<uuid:purchase_id>/", views.payment_success, name="payment_success"),
    path("razorpay/webhook/", views.razorpay_webhook, name="razorpay_webhook"),
]
