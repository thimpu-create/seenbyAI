from django import forms


class CheckoutForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-[#E4E0D4] text-[#3A6B52] focus:ring-[#3A6B52]",
            }
        ),
    )
