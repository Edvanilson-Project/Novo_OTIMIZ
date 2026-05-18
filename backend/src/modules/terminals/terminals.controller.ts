import {
  Controller,
  Get,
  Post,
  Patch,
  Delete,
  Param,
  Body,
  ParseIntPipe,
  UseGuards,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { TerminalsService } from './terminals.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('terminals')
@UseGuards(JwtAuthGuard)
export class TerminalsController {
  constructor(private readonly service: TerminalsService) {}

  @Get()
  findAll() {
    return this.service.findAll();
  }

  /** Lista apenas terminais marcados como depósito/garagem. Usado pelo planner e formulário de veículos. */
  @Get('depots')
  findDepots() {
    return this.service.findDepots();
  }

  @Get(':id')
  findOne(@Param('id', ParseIntPipe) id: number) {
    return this.service.findOne(id);
  }

  @Post()
  create(@Body() body: Record<string, any>) {
    return this.service.create(body);
  }

  @Patch(':id')
  update(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: Record<string, any>,
  ) {
    return this.service.update(id, body);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  remove(@Param('id', ParseIntPipe) id: number) {
    return this.service.remove(id);
  }
}
