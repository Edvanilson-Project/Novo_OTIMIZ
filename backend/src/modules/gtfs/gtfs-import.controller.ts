import {
  Controller,
  Post,
  UploadedFile,
  UseGuards,
  UseInterceptors,
  BadRequestException,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { GtfsImportService } from './gtfs-import.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('gtfs')
@UseGuards(JwtAuthGuard)
export class GtfsImportController {
  constructor(private readonly gtfsImportService: GtfsImportService) {}

  @Post('import')
  @UseInterceptors(
    FileInterceptor('file', { limits: { fileSize: 50 * 1024 * 1024 } }),
  )
  async import(@UploadedFile() file: Express.Multer.File) {
    if (!file) throw new BadRequestException('Arquivo GTFS (ZIP) não enviado.');
    return this.gtfsImportService.importFromBuffer(file.buffer);
  }
}
