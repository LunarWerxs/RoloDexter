import { generate_language as coreGenerateLanguage } from "./index.js";
import type { GenerateLanguageOptions, LanguageData } from "./index.js";

export {
  __all__,
  __version__,
  SUPPORTED_LANGUAGES,
  AddressNormalizer,
  BooleanNormalizer,
  CanonicalField,
  ContactMapper,
  EmailNormalizer,
  ExactMatchStrategy,
  FieldMatch,
  FuzzyMatchStrategy,
  HeuristicMatchStrategy,
  ListNormalizer,
  MappingProfile,
  MappingResult,
  MappingSchema,
  MatchStrategy,
  MatchType,
  NameNormalizer,
  NormalizationError,
  NormalizedMatchStrategy,
  NumberType,
  PatternLoadError,
  PatternRegistry,
  PhoneNormalizer,
  PhoneNumber,
  PhoneNumberMatch,
  PhoneNumberMatcher,
  PostalCodeNormalizer,
  RolodexterError,
  StringNormalizer,
  format_e164,
  format_international,
  format_national,
  is_number_match,
  is_valid,
  normalize_value,
  number_type,
  parse,
} from "./index.js";

export function generate_language(langCode: string, options: GenerateLanguageOptions = {}): LanguageData {
  if (arguments.length < 1) {
    throw new TypeError("generate_language() missing 1 required positional argument: 'lang_code'");
  }
  if (arguments.length > 2) {
    throw new TypeError(`generate_language() takes 1 positional argument but ${arguments.length} ${arguments.length === 1 ? "was" : "were"} given`);
  }
  return coreGenerateLanguage(langCode, options);
}
