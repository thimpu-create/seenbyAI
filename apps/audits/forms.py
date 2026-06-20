from urllib.parse import urlparse

from django import forms


INPUT_CLASS = (
    "block w-full rounded-md border border-[#E4E0D4] bg-white px-3 py-2.5 text-sm "
    "text-[#13192B] shadow-sm outline-none transition placeholder:text-[#8B8578] "
    "focus:border-[#3A6B52] focus:ring-4 focus:ring-[#E9F0EA]"
)


class AuditForm(forms.Form):
    url = forms.CharField(
        label="Website URL",
        max_length=500,
        widget=forms.TextInput(
            attrs={
                "placeholder": "https://example.com",
                "autocomplete": "url",
                "inputmode": "url",
                "class": INPUT_CLASS,
            }
        ),
    )

    def clean_url(self):
        url = self.cleaned_data["url"].strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        parsed = urlparse(url)
        if not parsed.netloc or "." not in parsed.netloc:
            raise forms.ValidationError("Enter a valid website URL.")
        if parsed.scheme not in {"http", "https"}:
            raise forms.ValidationError("Only http and https URLs are supported.")
        return url.rstrip("/")
