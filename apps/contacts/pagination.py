from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_page_size(self, request):
        requested = request.query_params.get(self.page_size_query_param)
        if requested is not None:
            try:
                requested_size = int(requested)
            except (TypeError, ValueError) as exc:
                raise ValidationError({"page_size": "page_size must be an integer."}) from exc
            if requested_size > self.max_page_size:
                raise ValidationError(
                    {"page_size": f"Maximum page_size is {self.max_page_size}."}
                )
        return super().get_page_size(request)
