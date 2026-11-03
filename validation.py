import re


class EmailValidator:
    EMAIL_PATTERN = r'^[a-zA-Z0-9._%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    @staticmethod
    def is_valid_email(email):
        if not email or not isinstance(email, str):
            return False, "Email is required"

        #remove leading/trailing whitespace
        email = email.strip()

        #check length constraints
        if len(email) < 5:
            return False, "Email too short (minimum 5 characters)"

        if len(email) > 254:
            return False, "Email too long (maximum 254 characters)"

        #apply regex pattern
        if not re.match(EmailValidator.EMAIL_PATTERN, email):
            return False, "Invalid email format. Must be like: user@example.com"

        #check for consecutive dots
        if '..' in email:
            return False, "Email cannot contain consecutive dots"

        #check local part (before @) length
        local_part = email.split('@')[0]
        if len(local_part) > 64:
            return False, "Email username too long (maximum 64 characters)"

        return True, ""

    @staticmethod
    def extract_domain(email):
        is_valid, _ = EmailValidator.is_valid_email(email)
        if not is_valid:
            return None

        return email.split('@')[1]

    '''
    @staticmethod
    def is_university_email(email):
        university_domains = [
            'open.ac.uk',
            'student.open.ac.uk',
            'ac.uk',
            'edu'
        ]

        domain = EmailValidator.extract_domain(email)
        if not domain:
            return False

        #check if domain ends with any university domain
        return any(domain.endswith(uni_domain) for uni_domain in university_domains)
    '''
