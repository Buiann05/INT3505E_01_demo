from flask import Flask, request, jsonify, make_response, Response
from flask_swagger_ui import get_swaggerui_blueprint
from datetime import datetime, timedelta
from functools import wraps
import json
import os
import base64
import math
import time
import logging
from logging.handlers import RotatingFileHandler

# SECURITY & MONITORING IMPORTS
from prometheus_flask_exporter import PrometheusMetrics
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

# SETUP LOGGING (Thay thế Winston trong Node.js)
# Cấu hình log: ghi ra file và console
log_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')

#File handler: tối đa 1MB, lưu 3 file backup
file_handler = RotatingFileHandler('app.log', maxBytes=1_000_000, backupCount=3)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

# Apply handlers to root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# SETUP RATE LIMITING
# Giới hạn request dựa trên IP người dùng
limiter = Limiter (
    get_remote_address,
    app=app,
    default_limits=["200 per day", "60 per hour"], # Mặc định cho toàn bộ API
    storage_uri="memory://", # Lưu trữ trong RAM (production nên dung Redis)
)

# SETUP PROMETHEUS METRICS
# Tự động đo lường request duration, count và expose tại /metrics
metrics = PrometheusMetrics(app)
metrics.info('app_info', 'Library API info', version='2.0.0')

# File lưu trữ dữ liệu
DATA_FILE = 'library_data.json'
V1_SUNSET_DATE = '2025-12-01'  # v1 retirement date
V1_DEPRECATION_DATE = '2025-01-01'  # v1 deprecation announcement

# Swagger UI Configuration
SWAGGER_URL = '/api/docs'
API_URL = '/static/openapi.yaml'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Library Management API with Pagination",
        'layout': "BaseLayout",
        'deepLinking': True
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Data Management

def init_data():
    # Khởi tạo dữ liệu mẫu


    if not os.path.exists(DATA_FILE):
        data = {
            'books': [
                {
                    'id': i,
                    'isbn': f'978-0-{1000+i}-{i*10:04d}-{i%10}',
                    'title': f'Book Title {i}',
                    'author': f'Author {(i-1)%5 + 1}',
                    'category': ['Programming', 'Database', 'Web Development', 'AI/ML', 'Security'][i%5],
                    'publisher': f'Publisher {(i-1)%3 + 1}',
                    'publishYear': 2020 + (i % 5),
                    'quantity': 5 + (i % 3),
                    'available': 3 + (i % 3),
                    'price': 100000 + (i * 10000),
                    'description': f'Description for book {i}',
                    'createdAt': (datetime.now() - timedelta(days=100-i)).isoformat() + 'Z'
                }
                for i in range(1, 51)  # 50 sách mẫu
            ],
            'borrowings': []
        }
        save_data(data)
        print(f" Đã khởi tạo {len(data['books'])} sách mẫu")
    return load_data()

def load_data():
    if not os.path.exists(DATA_FILE):
        return {'books': [], 'borrowings': []}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def deprecated(sunset_date, migration_url, version):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response = f(*args, **kwargs)
            
            if isinstance(response, tuple):
                data, status_code = response
                
                # --- FIX START: Kiểm tra xem data đã là Response object chưa ---
                if isinstance(data, Response):
                    # Nếu data đã là Response (do hàm gốc gọi jsonify rồi), dùng luôn
                    resp = make_response(data, status_code)
                else:
                    # Nếu data là dict/list thuần túy, mới bọc jsonify
                    resp = make_response(jsonify(data), status_code)
                
            else:
                resp = make_response(response)
            
            resp.headers['Deprecation'] = 'true'
            resp.headers['Sunset'] = sunset_date
            resp.headers['Link'] = f'<{migration_url}>; rel="alternate"'
            resp.headers['Warning'] = (
                f'299 - "API {version} is deprecated and will be removed on {sunset_date}. '
                f'Please migrate to the latest version."'
            )
            
            return resp
        return decorated_function
    return decorator

# MIDDLEWARE FOR LOGGING REQUESTS
@app.before_request
def start_timer():
    request.start_time = time.time()

@app.after_request
def log_request(response):
    if request.path.startswith('/static') or request.path.startswith('/api/docs') or request.path == '/metrics':
        return response
    
    # Tính thời gian xử lý
    duration = time.time() - request.start_time
    
    # Log chi tiết request
    log_message = f"{request.remote_addr} - {request.method} {request.path} - {response.status_code} - {duration:.4f}s"
    
    if response.status_code >= 400:
        logger.warning(log_message)
    else:
        logger.info(log_message)
        
    return response

@app.before_request
def check_version():
    path = request.path
    
    # Check if accessing v1 after sunset date
    if '/v1/' in path:
        sunset = datetime.strptime(V1_SUNSET_DATE, '%Y-%m-%d')
        if datetime.now() > sunset:
            return jsonify({
                'error': {
                    'code': 'version_retired',
                    'message': f'API v1 has been retired as of {V1_SUNSET_DATE}',
                    'deprecatedVersion': 'v1',
                    'currentVersion': 'v2',
                    'migrationGuide': 'https://docs.library.com/migration/v1-to-v2',
                    'supportEmail': 'api-support@library.com'
                }
            }), 410  # 410 Gone
        
def format_book_v1(book):
    return {
        'book_id': book['id'],
        'book_title': book['title'],
        'book_author': book['author'],
        'total_quantity': book['quantity'],
        'available_quantity': book['available'],
        'created_date': book.get('createdAt', '')
    }

def format_book_v2(book):
    return {
        'id': book['id'],
        'title': book['title'],
        'author': book['author'],
        'quantity': book['quantity'],
        'available': book['available'],
        'createdAt': book.get('createdAt', datetime.now().isoformat()),
        'links': {
            'self': f'/api/v2/books/{book["id"]}',
            'borrowings': f'/api/v2/books/{book["id"]}/borrowings'
        }
    }

def add_deprecation_warning_v1(data):
    if isinstance(data, dict):
        data['_deprecation'] = {
            'deprecated': True,
            'sunsetDate': V1_SUNSET_DATE,
            'message': f'API v1 is deprecated and will be retired on {V1_SUNSET_DATE}',
            'migrationGuide': 'https://docs.library.com/migration/v1-to-v2',
            'alternativeVersion': 'v2',
            'alternativeUrl': request.path.replace('/v1/', '/v2/')
        }
    return data

# Pagination Utilities 

def encode_cursor(book_id):
    cursor_data = {'id': book_id}
    return base64.b64encode(json.dumps(cursor_data).encode()).decode()

def decode_cursor(cursor):
    try:
        cursor_data = json.loads(base64.b64decode(cursor).decode())
        return cursor_data.get('id')
    except:
        return None

def paginate_offset(items, limit, offset):
    total = len(items)
    paginated_items = items[offset:offset + limit]
    
    return {
        'data': paginated_items,
        'pagination': {
            'total': total,
            'limit': limit,
            'offset': offset,
            'currentPage': (offset // limit) + 1 if limit > 0 else 1,
            'totalPages': math.ceil(total / limit) if limit > 0 else 1
        }
    }

def paginate_page(items, page, size):
    offset = (page - 1) * size
    total = len(items)
    paginated_items = items[offset:offset + size]
    
    return {
        'data': paginated_items,
        'page': {
            'number': page,
            'size': size,
            'totalElements': total,
            'totalPages': math.ceil(total / size) if size > 0 else 1
        }
    }

def paginate_cursor(items, cursor, limit):
    start_index = 0
    
    if cursor:
        cursor_id = decode_cursor(cursor)
        if cursor_id:
            # Find index of item with cursor_id
            for i, item in enumerate(items):
                if item['id'] == cursor_id:
                    start_index = i + 1
                    break
    
    # Get items + 1 to check if there's next page
    paginated_items = items[start_index:start_index + limit + 1]
    
    has_next = len(paginated_items) > limit
    if has_next:
        paginated_items = paginated_items[:limit]
    
    next_cursor = None
    if has_next and paginated_items:
        next_cursor = encode_cursor(paginated_items[-1]['id'])
    
    prev_cursor = None
    if start_index > 0:
        prev_id = items[start_index - 1]['id'] if start_index > 0 else None
        if prev_id:
            prev_cursor = encode_cursor(prev_id)
    
    return {
        'data': paginated_items,
        'pagination': {
            'nextCursor': next_cursor,
            'prevCursor': prev_cursor,
            'hasNext': has_next,
            'hasPrev': start_index > 0,
            'limit': limit
        }
    }

# Search & Filter Utilities 

def search_books(books, query):
    # Tìm kiếm sách theo title, author, isbn
    if not query:
        return books
    
    query = query.lower()
    return [
        book for book in books
        if query in book['title'].lower() or
           query in book['author'].lower() or
           query in book['isbn'].lower() or
           query in book.get('description', '').lower()
    ]

def filter_books(books, filters):
    # Lọc sách theo category, author, year
    result = books
    
    if filters.get('category'):
        result = [b for b in result if b['category'] == filters['category']]
    
    if filters.get('author'):
        result = [b for b in result if filters['author'].lower() in b['author'].lower()]
    
    if filters.get('minYear'):
        result = [b for b in result if b['publishYear'] >= int(filters['minYear'])]
    
    if filters.get('maxYear'):
        result = [b for b in result if b['publishYear'] <= int(filters['maxYear'])]
    
    if filters.get('available'):
        if filters['available'].lower() == 'true':
            result = [b for b in result if b['available'] > 0]
    
    return result

def sort_books(books, sort_by, order):
    # Sắp xếp sách
    valid_fields = ['id', 'title', 'author', 'publishYear', 'price', 'createdAt']
    
    if sort_by not in valid_fields:
        sort_by = 'id'
    
    reverse = (order == 'desc')
    
    return sorted(books, key=lambda x: x.get(sort_by, ''), reverse=reverse)

# ROOT ENDPOINT 

@app.route('/')
def home():
    return jsonify({
        'service': 'Library Management API',
        'versions': {
            'v1': {
                'status': 'deprecated',
                'baseUrl': '/api/v1',
                'deprecatedSince': V1_DEPRECATION_DATE,
                'sunsetDate': V1_SUNSET_DATE,
                'daysRemaining': (datetime.strptime(V1_SUNSET_DATE, '%Y-%m-%d') - datetime.now()).days,
                'documentation': 'https://docs.library.com/v1'
            },
            'v2': {
                'status': 'stable',
                'baseUrl': '/api/v2',
                'documentation': 'https://docs.library.com/v2'
            }
        },
        'migrationGuide': 'https://docs.library.com/migration'
    })

# BOOKS API - OFFSET/LIMIT 

@app.route('/api/books', methods=['GET'])
@limiter.limit("10 per minute") # Rate Limit riêng cho endpoint này
def api_get_books_offset():
    """GET /api/books - Offset/Limit Pagination
    
    Query Parameters:
    - limit: số items per page (default: 10, max: 100)
    - offset: vị trí bắt đầu (default: 0)
    - sort: field để sort (title, author, publishYear, price, createdAt)
    - order: asc hoặc desc (default: asc)
    """
    try:
        # Get parameters
        limit = min(int(request.args.get('limit', 10)), 100)
        offset = max(int(request.args.get('offset', 0)), 0)
        sort_by = request.args.get('sort', 'id')
        order = request.args.get('order', 'asc')
        
        # Load and sort data
        data = load_data()
        books = sort_books(data['books'], sort_by, order)
        
        # Paginate
        result = paginate_offset(books, limit, offset)
        
        print(f" Offset pagination: limit={limit}, offset={offset}, total={result['pagination']['total']}")
        return jsonify(result), 200
        
    except ValueError as e:
        return jsonify({'error': 'Invalid parameters'}), 400
    except Exception as e:
        print(f" Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# BOOKS API - PAGE NUMBER 

@app.route('/api/books/pages', methods=['GET'])
@limiter.limit("10 per minute")
def api_get_books_pages():
    """GET /api/books/pages - Page Number Pagination
    
    Query Parameters:
    - page: số trang (default: 1)
    - size: số items per page (default: 10, max: 100)
    - sort: field để sort
    - order: asc hoặc desc
    """
    try:
        # Get parameters
        page = max(int(request.args.get('page', 1)), 1)
        size = min(int(request.args.get('size', 10)), 100)
        sort_by = request.args.get('sort', 'id')
        order = request.args.get('order', 'asc')
        
        # Load and sort data
        data = load_data()
        books = sort_books(data['books'], sort_by, order)
        
        # Paginate
        result = paginate_page(books, page, size)
        
        print(f" Page pagination: page={page}, size={size}, total={result['page']['totalElements']}")
        return jsonify(result), 200
        
    except ValueError as e:
        return jsonify({'error': 'Invalid parameters'}), 400
    except Exception as e:
        print(f" Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# BOOKS API - CURSOR BASED

@app.route('/api/books/cursor', methods=['GET'])
def api_get_books_cursor():
    """GET /api/books/cursor - Cursor-based Pagination
    
    Query Parameters:
    - cursor: cursor token (optional)
    - limit: số items per page (default: 10, max: 100)
    - sort: field để sort
    - order: asc hoặc desc
    """
    try:
        # Get parameters
        cursor = request.args.get('cursor')
        limit = min(int(request.args.get('limit', 10)), 100)
        sort_by = request.args.get('sort', 'id')
        order = request.args.get('order', 'asc')
        
        # Load and sort data
        data = load_data()
        books = sort_books(data['books'], sort_by, order)
        
        # Paginate
        result = paginate_cursor(books, cursor, limit)
        
        print(f" Cursor pagination: cursor={cursor[:10] if cursor else 'None'}..., limit={limit}")
        return jsonify(result), 200
        
    except ValueError as e:
        return jsonify({'error': 'Invalid parameters'}), 400
    except Exception as e:
        print(f" Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# SEARCH API 

@app.route('/api/search', methods=['GET'])
@limiter.limit("5 per minute") 
def api_search_books():
    """GET /api/search - Tìm kiếm và lọc sách
    
    Query Parameters:
    - q: search query (tìm trong title, author, isbn, description)
    - category: lọc theo category
    - author: lọc theo author
    - minYear: năm xuất bản tối thiểu
    - maxYear: năm xuất bản tối đa
    - available: chỉ lấy sách còn (true/false)
    - sort: field để sort
    - order: asc/desc
    - limit: items per page
    - offset: vị trí bắt đầu
    """
    try:
        # Get search parameters
        query = request.args.get('q', '').strip()
        
        # Get filter parameters
        filters = {
            'category': request.args.get('category'),
            'author': request.args.get('author'),
            'minYear': request.args.get('minYear'),
            'maxYear': request.args.get('maxYear'),
            'available': request.args.get('available')
        }
        
        # Get pagination parameters
        limit = min(int(request.args.get('limit', 10)), 100)
        offset = max(int(request.args.get('offset', 0)), 0)
        sort_by = request.args.get('sort', 'id')
        order = request.args.get('order', 'asc')
        
        # Load data
        data = load_data()
        books = data['books']
        
        # Apply search
        if query:
            books = search_books(books, query)
            print(f" Search: '{query}' → {len(books)} results")
        
        # Apply filters
        books = filter_books(books, filters)
        print(f" Filters applied → {len(books)} results")
        
        # Sort
        books = sort_books(books, sort_by, order)
        
        # Paginate
        result = paginate_offset(books, limit, offset)
        
        # Add search metadata
        result['search'] = {
            'query': query,
            'filters': {k: v for k, v in filters.items() if v},
            'resultsFound': len(books)
        }
        
        return jsonify(result), 200
        
    except ValueError as e:
        return jsonify({'error': 'Invalid parameters'}), 400
    except Exception as e:
        print(f" Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# BOOK DETAILS

@app.route('/api/v1/books', methods=['GET'])
@deprecated(V1_SUNSET_DATE, '/api/v2/books', 'v1')
def get_books_v1():
    """
    API v1 - Get all books
    DEPRECATED: Will be removed on 2025-12-01
    Use /api/v2/books instead
    """
    data = load_data()
    books = [format_book_v1(book) for book in data['books']]
    
    result = {
        'status': 'success',
        'data': books,
        'count': len(books)
    }
    
    # Add deprecation warning
    result = add_deprecation_warning_v1(result)
    
    print(f" v1 API called: GET /api/v1/books (DEPRECATED)")
    return jsonify(result), 200

@app.route('/api/v1/books/<int:book_id>', methods=['GET'])
@deprecated(V1_SUNSET_DATE, '/api/v2/books', 'v1')
def get_book_v1(book_id):
    """
    API v1 - Get book by ID
    DEPRECATED: Use /api/v2/books/{id} instead
    """
    data = load_data()
    book = next((b for b in data['books'] if b['id'] == book_id), None)
    
    if not book:
        result = {
            'status': 'error',
            'message': f'Book with book_id {book_id} not found'
        }
        result = add_deprecation_warning_v1(result)
        return jsonify(result), 404
    
    result = {
        'status': 'success',
        'data': format_book_v1(book)
    }
    result = add_deprecation_warning_v1(result)
    
    print(f" v1 API called: GET /api/v1/books/{book_id} (DEPRECATED)")
    return jsonify(result), 200

# BOOK CREATE/UPDATE/DELETE

@app.route('/api/books', methods=['POST'])
@limiter.limit("3 per minute")
def create_book_v1():
    """
    API v1 - Create book
    DEPRECATED: Use /api/v2/books instead
    """
    if not request.json:
        result = add_deprecation_warning_v1({
            'status': 'error',
            'message': 'Request body must be JSON'
        })
        return jsonify(result), 400
    
    # v1 uses snake_case
    required = ['book_title', 'book_author', 'total_quantity']
    for field in required:
        if field not in request.json:
            result = add_deprecation_warning_v1({
                'status': 'error',
                'message': f'Missing required field: {field}'
            })
            return jsonify(result), 400
    
    data = load_data()
    
    new_book = {
        'id': max([b['id'] for b in data['books']], default=0) + 1,
        'title': request.json['book_title'],
        'author': request.json['book_author'],
        'quantity': int(request.json['total_quantity']),
        'available': int(request.json['total_quantity']),
        'createdAt': datetime.now().isoformat()
    }
    
    data['books'].append(new_book)
    save_data(data)
    
    result = {
        'status': 'success',
        'message': 'Book created successfully',
        'data': format_book_v1(new_book)
    }
    result = add_deprecation_warning_v1(result)
    
    print(f" v1 API called: POST /api/v1/books (DEPRECATED)")
    return jsonify(result), 201

@app.route('/api/v2/books', methods=['GET'])
@limiter.limit("30 per minute")
def get_books_v2():
    """
    API v2 - Get all books
    Current stable version
    """
    data = load_data()
    
    # Pagination support (v2 feature)
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = max(int(request.args.get('offset', 0)), 0)
    
    books = data['books'][offset:offset + limit]
    formatted_books = [format_book_v2(book) for book in books]
    
    result = {
        'data': formatted_books,
        'pagination': {
            'limit': limit,
            'offset': offset,
            'total': len(data['books']),
            'hasMore': (offset + limit) < len(data['books'])
        },
        'links': {
            'self': f'/api/v2/books?limit={limit}&offset={offset}'
        }
    }
    
    if result['pagination']['hasMore']:
        next_offset = offset + limit
        result['links']['next'] = f'/api/v2/books?limit={limit}&offset={next_offset}'
    
    print(f" v2 API called: GET /api/v2/books")
    return jsonify(result), 200

@app.route('/api/v2/books/<int:book_id>', methods=['GET'])
def get_book_v2(book_id):
    """
    API v2 - Get book by ID
    Current stable version
    """
    data = load_data()
    book = next((b for b in data['books'] if b['id'] == book_id), None)
    
    if not book:
        return jsonify({
            'error': {
                'code': 'not_found',
                'message': f'Book with ID {book_id} not found',
                'type': 'resource_not_found'
            }
        }), 404
    
    print(f" v2 API called: GET /api/v2/books/{book_id}")
    return jsonify(format_book_v2(book)), 200

@app.route('/api/v2/books', methods=['POST'])
@limiter.limit("5 per minute")
def create_book_v2():
    """
    API v2 - Create book
    Current stable version
    """
    if not request.json:
        return jsonify({
            'error': {
                'code': 'invalid_request',
                'message': 'Request body must be JSON',
                'type': 'validation_error'
            }
        }), 400
    
    # v2 uses camelCase
    required = ['title', 'author', 'quantity']
    missing = [f for f in required if f not in request.json]
    
    if missing:
        return jsonify({
            'error': {
                'code': 'missing_fields',
                'message': 'Missing required fields',
                'type': 'validation_error',
                'fields': missing
            }
        }), 400
    
    data = load_data()
    
    new_book = {
        'id': max([b['id'] for b in data['books']], default=0) + 1,
        'title': request.json['title'],
        'author': request.json['author'],
        'quantity': int(request.json['quantity']),
        'available': int(request.json['quantity']),
        'createdAt': datetime.now().isoformat()
    }
    
    data['books'].append(new_book)
    save_data(data)
    
    print(f" v2 API called: POST /api/v2/books")
    return jsonify(format_book_v2(new_book)), 201

@app.route('/api/v2/books/<int:book_id>', methods=['PUT'])
def update_book_v2(book_id):
    """API v2 - Update book"""
    data = load_data()
    book = next((b for b in data['books'] if b['id'] == book_id), None)
    
    if not book:
        return jsonify({
            'error': {
                'code': 'not_found',
                'message': f'Book with ID {book_id} not found'
            }
        }), 404
    
    # Update fields
    if 'title' in request.json:
        book['title'] = request.json['title']
    if 'author' in request.json:
        book['author'] = request.json['author']
    if 'quantity' in request.json:
        old_qty = book['quantity']
        new_qty = int(request.json['quantity'])
        book['quantity'] = new_qty
        book['available'] += (new_qty - old_qty)
    
    save_data(data)
    return jsonify(format_book_v2(book)), 200

@app.route('/api/v2/books/<int:book_id>', methods=['DELETE'])
def delete_book_v2(book_id):
    """API v2 - Delete book"""
    data = load_data()
    book = next((b for b in data['books'] if b['id'] == book_id), None)
    
    if not book:
        return jsonify({
            'error': {
                'code': 'not_found',
                'message': f'Book with ID {book_id} not found'
            }
        }), 404
    
    data['books'] = [b for b in data['books'] if b['id'] != book_id]
    save_data(data)
    
    return jsonify({
        'message': 'Book deleted successfully',
        'id': book_id
    }), 200

@app.route('/api/compare/<int:book_id>', methods=['GET'])
def compare_versions(book_id):
    """
    Compare how the same book is represented in v1 vs v2
    Useful for understanding migration
    """
    data = load_data()
    book = next((b for b in data['books'] if b['id'] == book_id), None)
    
    if not book:
        return jsonify({'error': 'Book not found'}), 404
    
    return jsonify({
        'raw': book,
        'v1_format': format_book_v1(book),
        'v2_format': format_book_v2(book),
        'differences': {
            'field_naming': 'v1 uses snake_case, v2 uses camelCase',
            'response_structure': 'v1 wraps in status/data, v2 returns directly',
            'links': 'v2 includes HATEOAS links, v1 does not',
            'deprecation': 'v1 includes deprecation warning, v2 does not'
        }
    })

@app.route('/api/migration/status', methods=['GET'])
def migration_status():
    """
    Show migration status and recommendations
    """
    # Get API version usage stats (simplified)
    # In production, track this in database
    
    days_until_sunset = (datetime.strptime(V1_SUNSET_DATE, '%Y-%m-%d') - datetime.now()).days
    
    return jsonify({
        'v1': {
            'status': 'deprecated',
            'sunsetDate': V1_SUNSET_DATE,
            'daysRemaining': days_until_sunset,
            'urgency': 'high' if days_until_sunset < 90 else 'medium'
        },
        'v2': {
            'status': 'stable',
            'recommended': True
        },
        'migration': {
            'guide': 'https://docs.library.com/migration',
            'breakingChanges': [
                'Field names: snake_case → camelCase',
                'Response format: wrapped → direct',
                'Pagination: not supported → cursor-based',
                'Error format: simple string → structured object'
            ],
            'estimatedEffort': '2-4 hours for typical integration',
            'support': {
                'email': 'api-support@library.com',
                'documentation': 'https://docs.library.com/v2',
                'examples': 'https://github.com/library/examples'
            }
        }
    })

# STATISTICS

@app.route('/api/stats', methods=['GET'])
def api_get_stats():
    """Thống kê hệ thống"""
    try:
        data = load_data()
        
        categories = {}
        for book in data['books']:
            cat = book['category']
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += 1
        
        stats = {
            'totalBooks': len(data['books']),
            'totalAvailable': sum(b['available'] for b in data['books']),
            'totalBorrowed': sum(b['quantity'] - b['available'] for b in data['books']),
            'booksByCategory': categories,
            'totalBorrowings': len(data['borrowings']),
            'activeBorrowings': len([b for b in data['borrowings'] if not b.get('returned', False)])
        }
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ERROR HANDLERS

@app.errorhandler(404)
def not_found(error):
    version = 'v2'
    if '/v1/' in request.path:
        version = 'v1'
    
    response = {
        'error': {
            'code': 'not_found',
            'message': 'Endpoint not found',
            'path': request.path,
            'method': request.method
        }
    }
    
    if version == 'v1':
        response = add_deprecation_warning_v1(response)
    
    return jsonify(response), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Lỗi server nội bộ'}), 500

# MAIN

if __name__ == '__main__':
    print("\n" + "="*70)
    print(" LIBRARY API - Multi-Version Support")
    print("="*70)
    
    # Initialize sample data
    if not os.path.exists(DATA_FILE):
        sample_data = {
            'books': [
                {'id': 1, 'title': 'Python Programming', 'author': 'John Smith', 'quantity': 5, 'available': 5, 'createdAt': '2024-01-15T10:00:00'},
                {'id': 2, 'title': 'Flask Web Development', 'author': 'Miguel Grinberg', 'quantity': 3, 'available': 3, 'createdAt': '2024-02-20T14:30:00'},
                {'id': 3, 'title': 'API Design Patterns', 'author': 'Jane Doe', 'quantity': 4, 'available': 4, 'createdAt': '2024-03-10T09:15:00'}
            ],
            'borrowings': []
        }
        save_data(sample_data)
        print(" Initialized sample data")
    
    sunset_days = (datetime.strptime(V1_SUNSET_DATE, '%Y-%m-%d') - datetime.now()).days
    
    print("\n API Versions:")
    print(f"   v1 (DEPRECATED): http://127.0.0.1:5000/api/v1/books")
    print(f"   v2 (STABLE):     http://127.0.0.1:5000/api/v2/books")
    
    print(f"\n API v1 Status:")
    print(f"   - Deprecated since: {V1_DEPRECATION_DATE}")
    print(f"   - Sunset date: {V1_SUNSET_DATE}")
    print(f"   - Days remaining: {sunset_days}")
    print(f"   - Will return 410 Gone after sunset")
    
    print(f"\n API v2 Status:")
    print(f"   - Status: Stable")
    print(f"   - Recommended for all new integrations")
    
    print("\n Comparison:")
    print("   http://127.0.0.1:5000/api/compare/1")
    
    print("\n Migration Status:")
    print("   http://127.0.0.1:5000/api/migration/status")
    
    print("\n Test Examples:")
    print("   # v1 (deprecated)")
    print("   curl http://127.0.0.1:5000/api/v1/books")
    print()
    print("   # v2 (stable)")
    print("   curl http://127.0.0.1:5000/api/v2/books")
    
    print(f"\n Monitoring & Logging:")
    print(f"   - Metrics:       http://127.0.0.1:5000/metrics")
    print(f"   - Log File:      app.log (Rotating, max 1MB)")
    print(f"   - Rate Limiting: Enabled (e.g., 200/day, 60/hour)")
    
    print("\n Test Examples:")
    print("   # Normal Request")
    print("   curl http://127.0.0.1:5000/api/v2/books")
    print()
    print("   # Test Rate Limit (Run multiple times fast)")
    print("   curl http://127.0.0.1:5000/api/search?q=python")

    print("\n Stop: Ctrl+C")
    print("="*70 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)