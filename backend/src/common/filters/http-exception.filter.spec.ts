import { HttpException, HttpStatus } from '@nestjs/common';
import { GlobalExceptionFilter } from './http-exception.filter';

describe('GlobalExceptionFilter', () => {
  let filter: GlobalExceptionFilter;
  let mockResponse: any;
  let mockRequest: any;
  let mockHost: any;

  beforeEach(() => {
    filter = new GlobalExceptionFilter();
    mockResponse = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
    mockRequest = { method: 'GET', url: '/test' };
    mockHost = {
      switchToHttp: jest.fn().mockReturnValue({
        getResponse: jest.fn().mockReturnValue(mockResponse),
        getRequest: jest.fn().mockReturnValue(mockRequest),
      }),
    };
  });

  it('handles HttpException with correct status', () => {
    const exception = new HttpException('Not Found', HttpStatus.NOT_FOUND);
    filter.catch(exception, mockHost);
    expect(mockResponse.status).toHaveBeenCalledWith(404);
    expect(mockResponse.json).toHaveBeenCalledWith(
      expect.objectContaining({ statusCode: 404, path: '/test' }),
    );
  });

  it('handles generic Error with 500 status', () => {
    const exception = new Error('Internal failure');
    filter.catch(exception, mockHost);
    expect(mockResponse.status).toHaveBeenCalledWith(500);
    expect(mockResponse.json).toHaveBeenCalledWith(
      expect.objectContaining({
        statusCode: 500,
        message: 'Erro interno do servidor',
      }),
    );
  });

  it('handles HttpException with object response', () => {
    const exception = new HttpException(
      { message: 'Validation failed', errors: [] },
      400,
    );
    filter.catch(exception, mockHost);
    expect(mockResponse.status).toHaveBeenCalledWith(400);
    const body = mockResponse.json.mock.calls[0][0];
    expect(body.message).toBe('Validation failed');
  });

  it('includes timestamp in response', () => {
    const exception = new HttpException('Conflict', HttpStatus.CONFLICT);
    filter.catch(exception, mockHost);
    const body = mockResponse.json.mock.calls[0][0];
    expect(body.timestamp).toBeTruthy();
    expect(new Date(body.timestamp).getTime()).toBeGreaterThan(0);
  });
});
