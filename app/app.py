from flask import Flask, request, jsonify
from flask_swagger_ui import get_swaggerui_blueprint
from datetime import datetime, timedelta
import json
import os
import base64
import math

app = Flask(__name__)

# File lưu trữ dữ liệu
DATA_FILE = 'library_data.json'

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
    """Khởi tạo dữ liệu mẫu"""
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
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Pagination Utilities 

def encode_cursor(book_id):
    """Encode cursor for cursor-based pagination"""
    cursor_data = {'id': book_id}
    return base64.b64encode(json.dumps(cursor_data).encode()).decode()

def decode_cursor(cursor):
    """Decode cursor"""
    try:
        cursor_data = json.loads(base64.b64decode(cursor).decode())
        return cursor_data.get('id')
    except:
        return None

def paginate_offset(items, limit, offset):
    """Offset-based pagination"""
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
    """Page number pagination"""
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
    """Cursor-based pagination"""
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
    """Tìm kiếm sách theo title, author, isbn"""
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
    """Lọc sách theo category, author, year"""
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
    """Sắp xếp sách"""
    valid_fields = ['id', 'title', 'author', 'publishYear', 'price', 'createdAt']
    
    if sort_by not in valid_fields:
        sort_by = 'id'
    
    reverse = (order == 'desc')
    
    return sorted(books, key=lambda x: x.get(sort_by, ''), reverse=reverse)

# ROOT ENDPOINT 

@app.route('/')
def home():
    return jsonify({
        'message': 'Library Management API with Pagination & Search',
        'version': '2.0.0',
        'documentation': f'http://127.0.0.1:5000{SWAGGER_URL}',
        'endpoints': {
            'books': {
                'GET /api/books': 'Danh sách sách (offset/limit pagination)',
                'GET /api/books/pages': 'Danh sách sách (page number pagination)',
                'GET /api/books/cursor': 'Danh sách sách (cursor-based pagination)',
                'GET /api/search': 'Tìm kiếm và lọc sách'
            }
        }
    }), 200

# BOOKS API - OFFSET/LIMIT 

@app.route('/api/books', methods=['GET'])
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

@app.route('/api/books/<int:book_id>', methods=['GET'])
def api_get_book(book_id):
    """Lấy chi tiết sách"""
    try:
        data = load_data()
        book = next((b for b in data['books'] if b['id'] == book_id), None)
        
        if not book:
            return jsonify({'error': f'Không tìm thấy sách với ID: {book_id}'}), 404
        
        print(f" Get book: {book['title']} (ID: {book_id})")
        return jsonify(book), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# BOOK CREATE/UPDATE/DELETE

@app.route('/api/books', methods=['POST'])
def api_create_book():
    """Thêm sách mới"""
    try:
        if not request.json:
            return jsonify({'error': 'Request phải là JSON'}), 400
        
        required = ['title', 'author', 'category', 'quantity']
        for field in required:
            if field not in request.json:
                return jsonify({'error': f'Thiếu field: {field}'}), 400
        
        data = load_data()
        
        new_book = {
            'id': max([b['id'] for b in data['books']], default=0) + 1,
            'isbn': request.json.get('isbn', ''),
            'title': request.json['title'],
            'author': request.json['author'],
            'category': request.json['category'],
            'publisher': request.json.get('publisher', ''),
            'publishYear': request.json.get('publishYear', datetime.now().year),
            'quantity': int(request.json['quantity']),
            'available': int(request.json['quantity']),
            'price': request.json.get('price', 0),
            'description': request.json.get('description', ''),
            'createdAt': datetime.now().isoformat() + 'Z'
        }
        
        data['books'].append(new_book)
        save_data(data)
        
        print(f"✅ Created book: {new_book['title']} (ID: {new_book['id']})")
        return jsonify(new_book), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/books/<int:book_id>', methods=['PUT'])
def api_update_book(book_id):
    """Cập nhật sách"""
    try:
        if not request.json:
            return jsonify({'error': 'Request phải là JSON'}), 400
        
        data = load_data()
        book = next((b for b in data['books'] if b['id'] == book_id), None)
        
        if not book:
            return jsonify({'error': f'Không tìm thấy sách ID: {book_id}'}), 404
        
        # Update fields
        for field in ['title', 'author', 'category', 'publisher', 'publishYear', 'description', 'price']:
            if field in request.json:
                book[field] = request.json[field]
        
        if 'quantity' in request.json:
            old_qty = book['quantity']
            new_qty = int(request.json['quantity'])
            book['quantity'] = new_qty
            book['available'] += (new_qty - old_qty)
        
        save_data(data)
        print(f" Updated book: {book['title']} (ID: {book_id})")
        return jsonify(book), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/books/<int:book_id>', methods=['DELETE'])
def api_delete_book(book_id):
    """Xóa sách"""
    try:
        data = load_data()
        book = next((b for b in data['books'] if b['id'] == book_id), None)
        
        if not book:
            return jsonify({'error': f'Không tìm thấy sách ID: {book_id}'}), 404
        
        data['books'] = [b for b in data['books'] if b['id'] != book_id]
        save_data(data)
        
        print(f"✅ Deleted book: {book['title']} (ID: {book_id})")
        return jsonify({'message': 'Xóa sách thành công'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
    return jsonify({'error': 'Endpoint không tồn tại'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Lỗi server nội bộ'}), 500

# MAIN

if __name__ == '__main__':
    print("\n" + "="*70)
    print("LIBRARY API - Pagination & Search")
    print("="*70)
    
    init_data()
    
    print("\n API Endpoints:")
    print("Home: http://127.0.0.1:5000/")
    print("Swagger: http://127.0.0.1:5000/api/docs")
    print("\n Books APIs:")
    print("      - Offset: GET /api/books?limit=10&offset=0")
    print("      - Page:   GET /api/books/pages?page=1&size=10")
    print("      - Cursor: GET /api/books/cursor?cursor=xxx&limit=10")
    print("Search: GET /api/search?q=python&category=Programming")
    print("Stats:  GET /api/stats")
    
    print("\n Test Examples:")
    print("   curl 'http://127.0.0.1:5000/api/books?limit=5&offset=0'")
    print("   curl 'http://127.0.0.1:5000/api/books/pages?page=2&size=10'")
    print("   curl 'http://127.0.0.1:5000/api/search?q=python&available=true'")
    
    print("\n Stop: Ctrl+C")
    print("="*70 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)