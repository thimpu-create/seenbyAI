from allauth.account.forms import LoginForm, ResetPasswordForm, SignupForm


INPUT_CLASS = (
    "block w-full rounded-md border border-[#E4E0D4] bg-white px-3 py-2.5 text-sm "
    "text-[#13192B] shadow-sm outline-none transition placeholder:text-[#8B8578] "
    "focus:border-[#3A6B52] focus:ring-4 focus:ring-[#E9F0EA]"
)
CHECKBOX_CLASS = "h-4 w-4 rounded border-[#E4E0D4] text-[#3A6B52] focus:ring-[#3A6B52]"


def _style_fields(form):
    for name, field in form.fields.items():
        if getattr(field.widget, "input_type", "") == "checkbox":
            field.widget.attrs.update({"class": CHECKBOX_CLASS})
        else:
            field.widget.attrs.update({"class": INPUT_CLASS})


class TailwindLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class TailwindSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class TailwindResetPasswordForm(ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
