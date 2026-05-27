class NoThrottle:
    def allow_request(self, request, view):
        return True

    def wait(self):
        return None
