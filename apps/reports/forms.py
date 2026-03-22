from django import forms

class SalesReportForm(forms.Form):
    STATUS_CHOICES = (
        ('', 'All Contracts'),
        ('active', 'Active Contracts'),
        ('completed', 'Completed Contracts'),
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'vDateField'}),
        required=True,
        label="From Date"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'vDateField'}),
        required=True,
        label="To Date"
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        label="Contract Status"
    )