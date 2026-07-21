import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  ImagePlus,
  Maximize2,
  Trash2,
  Unlink,
  Upload,
  X,
} from 'lucide-react';

import type { WizardCollegeItem } from '../../../schemas/wizard/step3-colleges';
import {
  hydrateWizardPicture,
  pictureDisplayFileName,
  pictureToApiPayload,
  rewriteStoredMediaUrl,
  sanitizeWizardPictureFilename,
  wizardPicturesStepSchema,
  type WizardPictureItem,
} from '../../../schemas/wizard/step6-pictures';
import { validatePictureFile } from '../../../schemas/wizard/shared';
import { apiFetch } from '../../../utils/api';
import SelectField from '../form/SelectField';
import WizardFieldError from './form/WizardFieldError';
import type { WizardStepHandle } from './form/wizardStepRef';
import EmptyListMessage from '../../ui/EmptyListMessage';
import {
  useWizardListStepDefaultsSync,
  useWizardStepSnapshot,
} from './form/wizardDirtyTracking';
import {
  wizardInputClass,
  wizardSectionClass,
  wizardSectionTitleClass,
} from './form/wizardFormStyles';
import { useConfirmation } from '../../../context/ConfirmationContext';
import WizardPicturesHierarchyTree from './WizardPicturesHierarchyTree';
import {
  assetsBecomingUnreferenced,
  clonePictureForCollege,
  collegeScopeKey,
  ensureCascadeCollegePictureClones,
  ensureUniqueCollegeLocalIds,
  expandInstitutionPictureUnlinkIndices,
  getCollegeOwnedPictureIndices,
  institutionScopeKey,
  pictureAssetKey,
  pictureScopeKey,
  pictureSelectionKey,
  remapPictureCollegeLocalIds,
  resolveCollegeLocalId,
  scopeKey,
  stampPictureScope,
  type WizardPicturesEntityScope,
} from './wizardPicturesScope';

interface InstitutionWizardStep6Props {
  institutionId: number | null;
  defaultPictures: WizardPictureItem[];
  /** When false (step hidden), skip R2 auto-restore so other steps' "Not added" badges stay stable. */
  isActive?: boolean;
  onPicturesChange?: (
    pictures: WizardPictureItem[],
    meta?: { collegePictureOverrides: string[] }
  ) => void;
  /** Persist gallery + college overrides to the draft immediately (e.g. after unlink). */
  onPersistPictures?: (
    pictures: WizardPictureItem[],
    meta: { collegePictureOverrides: string[] }
  ) => void | Promise<void>;
  colleges?: WizardCollegeItem[];
  institutionName?: string;
  defaultCollegeOverrides?: string[];
  layout?: 'flat' | 'hierarchy';
  onRemoveCollege?: (collegeLocalId: string) => void;
}

type PictureType = WizardPictureItem['picture_type'];

interface SelectedImage {
  file: File;
  warnings: string[];
}

interface UploadedPicture {
  url: string;
  caption: null;
  picture_type: PictureType;
  file_name: string;
  file_type: string;
  file_size: number;
  storage_key?: string | null;
}

const TYPE_OPTIONS = [
  { value: 'gallery', label: 'Gallery' },
  { value: 'logo', label: 'Logo' },
  { value: 'banner', label: 'Banner (Hero)' },
] as const;

const typeLabel = (pictureType: PictureType): string =>
  TYPE_OPTIONS.find(option => option.value === pictureType)?.label || 'Gallery';

const validateFormatForType = (file: File, pictureType: PictureType): string | null => {
  const baseError = validatePictureFile(file);
  if (baseError) return baseError;
  if (pictureType === 'logo' && !['image/svg+xml', 'image/png'].includes(file.type)) {
    return 'Logos must be SVG or PNG.';
  }
  if (pictureType === 'banner' && !['image/webp', 'image/jpeg'].includes(file.type)) {
    return 'Banner (Hero) images must be WebP or JPEG.';
  }
  if (pictureType === 'gallery' && !['image/webp', 'image/jpeg', 'image/jpg'].includes(file.type)) {
    return 'Gallery images must be WebP or JPEG.';
  }
  return null;
};

const readImageDimensions = (file: File): Promise<{ width: number; height: number } | null> =>
  new Promise(resolve => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve({ width: image.naturalWidth, height: image.naturalHeight });
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(null);
    };
    image.src = objectUrl;
  });

const dimensionWarnings = (
  pictureType: PictureType,
  dimensions: { width: number; height: number } | null
): string[] => {
  if (!dimensions) return ['Image dimensions could not be read.'];
  const { width, height } = dimensions;
  const ratio = width / height;
  const warnings: string[] = [];
  if (pictureType === 'logo' && (width < 200 || width > 300)) {
    warnings.push(`Logo width is ${width}px; 200–300px is recommended.`);
  }
  if (pictureType === 'banner') {
    if (width < 1800 || width > 2500) {
      warnings.push(`Banner width is ${width}px; 1800–2500px is recommended.`);
    }
    if (ratio < 2 || ratio > 3) {
      warnings.push(`Banner ratio is ${ratio.toFixed(2)}:1; use 2:1 to 3:1.`);
    }
  }
  if (pictureType === 'gallery') {
    if (width < 1200) {
      warnings.push(`Gallery width is ${width}px; at least 1200px is recommended.`);
    }
    const targetRatios = [1, 4 / 3, 3 / 2];
    if (!targetRatios.some(target => Math.abs(ratio - target) <= 0.08)) {
      warnings.push(`Ratio ${ratio.toFixed(2)}:1 differs from 1:1, 4:3, and 3:2.`);
    }
  }
  return warnings;
};

const InstitutionWizardStep6 = forwardRef<
  WizardStepHandle<WizardPictureItem[]>,
  InstitutionWizardStep6Props
>(
  (
    {
      institutionId,
      defaultPictures,
      isActive = false,
      onPicturesChange,
      onPersistPictures,
      colleges = [],
      institutionName = 'University',
      defaultCollegeOverrides = [],
      layout = 'hierarchy',
      onRemoveCollege,
    },
    ref
  ) => {
  const isHierarchy = layout === 'hierarchy';
  const openConfirm = useConfirmation();
  const scopedColleges = useMemo(
    () => ensureUniqueCollegeLocalIds(colleges),
    [colleges]
  );
  const [pictures, setPictures] = useState(defaultPictures);
  const [pictureType, setPictureType] = useState<PictureType>('gallery');
  const [selectedImages, setSelectedImages] = useState<SelectedImage[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deletingUrl, setDeletingUrl] = useState<string | null>(null);
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(() => new Set());
  const [selectedPictureKeys, setSelectedPictureKeys] = useState<Set<string>>(
    () => new Set()
  );
  const [previewPicture, setPreviewPicture] = useState<WizardPictureItem | null>(null);
  const [showImageRequirements, setShowImageRequirements] = useState(false);
  const [previewGallery, setPreviewGallery] = useState<WizardPictureItem[]>([]);
  const [activeScopeKey, setActiveScopeKey] = useState(institutionScopeKey());
  const [cascadeToColleges, setCascadeToColleges] = useState(true);
  const [collegeOverrides, setCollegeOverrides] = useState<Set<string>>(
    () => new Set(defaultCollegeOverrides)
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const skipNextDefaultsResetRef = useRef(false);
  const picturesRef = useRef(pictures);
  picturesRef.current = pictures;
  const collegeOverridesRef = useRef(collegeOverrides);
  collegeOverridesRef.current = collegeOverrides;

  useEffect(() => {
    const remapped = defaultCollegeOverrides.map(id => {
      const trimmed = id.trim();
      const match = scopedColleges.find(
        college =>
          resolveCollegeLocalId(college) === trimmed || college.name?.trim() === trimmed
      );
      return match ? resolveCollegeLocalId(match) : trimmed;
    });
    setCollegeOverrides(new Set(remapped));
    collegeOverridesRef.current = new Set(remapped);
  }, [defaultCollegeOverrides, scopedColleges]);

  const activeScope = useMemo((): WizardPicturesEntityScope => {
    if (activeScopeKey.startsWith('college:')) {
      const collegeLocalId = activeScopeKey.slice('college:'.length);
      const college = scopedColleges.find(
        item => resolveCollegeLocalId(item) === collegeLocalId
      );
      return {
        type: 'college',
        collegeLocalId,
        collegeName: college?.name || 'College',
      };
    }
    return { type: 'institution' };
  }, [activeScopeKey, scopedColleges]);

  const replacePictures = useCallback(
    (next: WizardPictureItem[], overrides?: string[]) => {
      const nextOverrides = overrides ?? [...collegeOverridesRef.current];
      collegeOverridesRef.current = new Set(nextOverrides);
      setPictures(next);
      setCollegeOverrides(new Set(nextOverrides));
      onPicturesChange?.(next, {
        collegePictureOverrides: nextOverrides,
      });
    },
    [onPicturesChange]
  );

  // Align college_local_id values with stable college ids. Do NOT backfill
  // cascade clones here — that would retroactively push university images onto
  // colleges that left override (or never received a given upload).
  useEffect(() => {
    if (!isHierarchy || scopedColleges.length === 0) return;
    const next = remapPictureCollegeLocalIds(picturesRef.current, scopedColleges);
    if (
      next.length === picturesRef.current.length &&
      next.every((item, index) => item === picturesRef.current[index])
    ) {
      return;
    }
    skipNextDefaultsResetRef.current = true;
    replacePictures(next);
  }, [isHierarchy, replacePictures, scopedColleges, pictures.length]);

  useEffect(() => {
    const availableUrls = new Set(
      pictures.map(picture => picture.url?.trim()).filter((url): url is string => Boolean(url))
    );
    setSelectedUrls(previous => {
      const next = new Set([...previous].filter(url => availableUrls.has(url)));
      return next.size === previous.size ? previous : next;
    });
    const availableKeys = new Set(pictures.map(pictureSelectionKey));
    setSelectedPictureKeys(previous => {
      const next = new Set([...previous].filter(key => availableKeys.has(key)));
      return next.size === previous.size ? previous : next;
    });
  }, [pictures]);

  const movePreview = useCallback(
    (direction: -1 | 1) => {
      setPreviewPicture(current => {
        if (!current) return current;
        const previewable = (
          previewGallery.length > 0 ? previewGallery : pictures
        ).filter(picture => Boolean(picture.url?.trim()));
        if (previewable.length < 2) return current;
        const currentIndex = previewable.findIndex(
          picture =>
            (current.local_id && picture.local_id === current.local_id) ||
            pictureSelectionKey(picture) === pictureSelectionKey(current) ||
            picture.url?.trim() === current.url?.trim()
        );
        const nextIndex =
          (Math.max(currentIndex, 0) + direction + previewable.length) %
          previewable.length;
        return previewable[nextIndex];
      });
    },
    [pictures, previewGallery]
  );

  useEffect(() => {
    if (!previewPicture) return;
    const handlePreviewKey = (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft') movePreview(-1);
      if (event.key === 'ArrowRight') movePreview(1);
      if (event.key === 'Escape') {
      setPreviewPicture(null);
      setPreviewGallery([]);
    }
    };
    window.addEventListener('keydown', handlePreviewKey);
    return () => window.removeEventListener('keydown', handlePreviewKey);
  }, [movePreview, previewPicture]);

  const getSnapshot = useCallback(
    () => ({
      pictures: pictures.map(pictureToApiPayload),
      college_picture_overrides: [...collegeOverrides].sort(),
    }),
    [collegeOverrides, pictures]
  );
  const { markClean, isDirty } = useWizardStepSnapshot(getSnapshot);
  const hydratedFromStorageRef = useRef(false);

  useEffect(() => {
    // Step 6 stays mounted while hidden. Only restore from object storage when the
    // Gallery tab is actually open — otherwise leftover R2 objects can write into
    // draft.payload.pictures and make the step navigator "Not added" badge flicker.
    if (!isActive || !institutionId || hydratedFromStorageRef.current) return;
    if (picturesRef.current.length > 0 || defaultPictures.length > 0) {
      hydratedFromStorageRef.current = true;
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const rows = await apiFetch(
          `academia/institutions/${institutionId}/pictures/assets`
        );
        if (cancelled || !Array.isArray(rows) || rows.length === 0) {
          if (!cancelled) hydratedFromStorageRef.current = true;
          return;
        }
        const restored = rows.map(row => hydrateWizardPicture(row));
        skipNextDefaultsResetRef.current = true;
        hydratedFromStorageRef.current = true;
        replacePictures(restored);
        markClean();
      } catch {
        // Keep empty gallery if storage listing is unavailable.
        if (!cancelled) hydratedFromStorageRef.current = true;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [defaultPictures.length, institutionId, isActive, markClean, replacePictures]);

  useWizardListStepDefaultsSync(
    defaultPictures,
    () => {
      // Uploads update parent draft immediately; ignore the echo reset that would
      // briefly clear the gallery with a stale empty defaults snapshot.
      if (skipNextDefaultsResetRef.current) {
        skipNextDefaultsResetRef.current = false;
        // Keep dirty tracking — parent draft echo must not mark this step clean.
        return false;
      }
      // Never wipe in-progress local uploads with an empty defaults payload.
      if (defaultPictures.length === 0 && picturesRef.current.length > 0) {
        return false;
      }
      setPictures(defaultPictures);
      setSelectedImages([]);
      setFileError(null);
    },
    markClean
  );

  useImperativeHandle(ref, () => ({
    validate: async () => {
      if (selectedImages.length > 0) {
        setListError('Upload or remove the selected images before saving the Gallery step.');
        return false;
      }
      const parsed = wizardPicturesStepSchema.safeParse(pictures);
      if (!parsed.success) {
        setListError(parsed.error.issues[0]?.message || 'Fix gallery image errors.');
        return false;
      }
      setListError(null);
      return true;
    },
    getValues: () => pictures.map(pictureToApiPayload),
    reset: values => {
      replacePictures(values.map(item => hydrateWizardPicture(item)));
      setSelectedImages([]);
      setFileError(null);
      markClean();
    },
    isDirty,
    markClean,
    getCollegePictureOverrides: () => [...collegeOverridesRef.current],
  }));

  const handleFileSelection = async (
    files: FileList | null,
    targetScope: WizardPicturesEntityScope = activeScope
  ) => {
    if (!files?.length) {
      setSelectedImages([]);
      setFileError(null);
      return;
    }
    const incoming = Array.from(files);
    if (incoming.length > 20) {
      setSelectedImages([]);
      setFileError('Select no more than 20 images at once.');
      return;
    }
    const errors: string[] = [];
    const accepted: SelectedImage[] = [];
    const writableScopeKey =
      targetScope.type === 'institution'
        ? institutionScopeKey()
        : collegeScopeKey(targetScope.collegeLocalId);
    const existingFileNames = new Set(
      picturesRef.current
        .filter(item => pictureScopeKey(item) === writableScopeKey)
        .flatMap(item => {
          const names: string[] = [];
          const name = (item.file_name || '').trim();
          if (name) {
            names.push(name.toLowerCase());
            names.push(sanitizeWizardPictureFilename(name).toLowerCase());
          }
          const key = pictureAssetKey(item);
          const parts = key.split('/').filter(Boolean);
          if (parts.length > 0) names.push(parts[parts.length - 1].toLowerCase());
          return names;
        })
    );
    const seenBatch = new Set<string>();

    for (const file of incoming) {
      const validationError = validateFormatForType(file, pictureType);
      if (validationError) {
        errors.push(`${file.name}: ${validationError}`);
        continue;
      }
      const sanitized = sanitizeWizardPictureFilename(file.name).toLowerCase();
      if (existingFileNames.has(sanitized) || seenBatch.has(sanitized)) {
        errors.push(
          `${file.name}: already linked here — duplicate images are not added again.`
        );
        continue;
      }
      seenBatch.add(sanitized);
      const dimensions = await readImageDimensions(file);
      accepted.push({ file, warnings: dimensionWarnings(pictureType, dimensions) });
    }

    setSelectedImages(accepted);
    setFileError(errors.length ? errors.join(' ') : null);
  };

  const clearSelection = () => {
    setSelectedImages([]);
    setFileError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const confirmUniversityCascadeImpact = async (actionLabel: string): Promise<boolean> => {
    if (!isHierarchy || !cascadeToColleges || scopedColleges.length === 0) return true;
    return openConfirm({
      title: 'Apply to all colleges?',
      message: `${actionLabel} will also apply to all child colleges (except overridden ones). Continue?`,
      confirmLabel: 'Yes',
      cancelLabel: 'No',
      variant: 'warning',
    });
  };

  const uploadSelectedImages = async (targetScope: WizardPicturesEntityScope = activeScope) => {
    if (!institutionId) {
      setFileError('Save the Institution step before uploading gallery images.');
      return;
    }
    if (!selectedImages.length) {
      setFileError('Select at least one image.');
      return;
    }

    if (isHierarchy) {
      setActiveScopeKey(scopeKey(targetScope));
    }

    if (
      targetScope.type === 'institution' &&
      !(await confirmUniversityCascadeImpact('Uploading these images'))
    ) {
      return;
    }

    const writableScopeKey =
      targetScope.type === 'institution'
        ? institutionScopeKey()
        : collegeScopeKey(targetScope.collegeLocalId);

    const existingInScope = picturesRef.current.filter(
      item => pictureScopeKey(item) === writableScopeKey
    );
    const existingAssetKeys = new Set(
      existingInScope.map(pictureAssetKey).filter(Boolean)
    );
    const existingFileNames = new Set<string>();
    for (const item of existingInScope) {
      const name = (item.file_name || '').trim();
      if (name) {
        existingFileNames.add(name.toLowerCase());
        existingFileNames.add(sanitizeWizardPictureFilename(name).toLowerCase());
      }
      // Also match by storage_key filename segment (type/filename).
      const key = pictureAssetKey(item);
      const parts = key.split('/').filter(Boolean);
      if (parts.length > 0) {
        existingFileNames.add(parts[parts.length - 1].toLowerCase());
      }
    }

    const uniqueSelected: SelectedImage[] = [];
    const duplicateNames: string[] = [];
    const seenBatchNames = new Set<string>();
    for (const selected of selectedImages) {
      const sanitized = sanitizeWizardPictureFilename(selected.file.name).toLowerCase();
      if (
        existingFileNames.has(sanitized) ||
        seenBatchNames.has(sanitized) ||
        [...existingAssetKeys].some(key => key.toLowerCase().endsWith(`/${sanitized}`))
      ) {
        duplicateNames.push(selected.file.name);
        continue;
      }
      seenBatchNames.add(sanitized);
      uniqueSelected.push(selected);
    }

    if (uniqueSelected.length === 0) {
      setFileError(
        duplicateNames.length === 1
          ? `"${duplicateNames[0]}" is already linked here. Duplicate images are not added again.`
          : `${duplicateNames.length} selected image${
              duplicateNames.length === 1 ? '' : 's'
            } are already linked here and were not added again: ${duplicateNames.join(', ')}.`
      );
      return;
    }

    setUploading(true);
    setFileError(
      duplicateNames.length
        ? `Skipped ${duplicateNames.length} duplicate image${
            duplicateNames.length === 1 ? '' : 's'
          } already linked here: ${duplicateNames.join(', ')}. Uploading the rest…`
        : null
    );
    try {
      const formData = new FormData();
      formData.append('picture_type', pictureType);
      uniqueSelected.forEach(({ file }) => formData.append('files', file));
      const response = await apiFetch(
        `academia/institutions/${institutionId}/pictures/upload`,
        { method: 'POST', body: formData }
      );
      const rows = (Array.isArray(response) ? response : []) as UploadedPicture[];
      if (rows.length === 0) {
        setFileError('Upload completed but no images were returned by the server.');
        return;
      }

      let nextOverrides = collegeOverrides;
      if (
        isHierarchy &&
        targetScope.type === 'college' &&
        !collegeOverrides.has(targetScope.collegeLocalId)
      ) {
        nextOverrides = new Set([...collegeOverrides, targetScope.collegeLocalId]);
        setCollegeOverrides(nextOverrides);
      }

      const uploadedAll = rows.map((row, index) => {
        const originalName = uniqueSelected[index]?.file.name?.trim();
        return stampPictureScope(
          hydrateWizardPicture({
            ...row,
            // Prefer the browser's original filename over the sanitized storage name.
            file_name: originalName || row.file_name,
          }),
          targetScope
        );
      });
      const skippedAfterUpload: string[] = [];
      const uploaded = uploadedAll.filter(picture => {
        const assetKey = pictureAssetKey(picture);
        if (!assetKey || existingAssetKeys.has(assetKey)) {
          skippedAfterUpload.push(pictureDisplayFileName(picture) || assetKey || 'image');
          return false;
        }
        existingAssetKeys.add(assetKey);
        return true;
      });

      if (uploaded.length === 0) {
        setFileError(
          `Those images are already linked here and were not added again.${
            skippedAfterUpload.length
              ? ` Skipped: ${[...new Set(skippedAfterUpload)].join(', ')}.`
              : ''
          }`
        );
        clearSelection();
        return;
      }

      const cascaded: WizardPictureItem[] = [];
      if (
        isHierarchy &&
        targetScope.type === 'institution' &&
        cascadeToColleges &&
        scopedColleges.length > 0
      ) {
        const seenCollegeIds = new Set<string>();
        for (const college of scopedColleges) {
          const collegeLocalId = resolveCollegeLocalId(college);
          if (!collegeLocalId || seenCollegeIds.has(collegeLocalId)) continue;
          seenCollegeIds.add(collegeLocalId);
          if (nextOverrides.has(collegeLocalId)) continue;
          const existingKeys = new Set(
            picturesRef.current
              .filter(item => pictureScopeKey(item) === collegeScopeKey(collegeLocalId))
              .map(pictureAssetKey)
              .filter(Boolean)
          );
          for (const picture of uploaded) {
            const assetKey = pictureAssetKey(picture);
            if (!assetKey || existingKeys.has(assetKey)) continue;
            existingKeys.add(assetKey);
            cascaded.push(clonePictureForCollege(picture, college));
          }
        }
      }

      const next = [...picturesRef.current, ...uploaded, ...cascaded];
      skipNextDefaultsResetRef.current = true;
      replacePictures(next, [...nextOverrides]);
      clearSelection();
      const allSkipped = [...duplicateNames, ...skippedAfterUpload];
      if (allSkipped.length > 0) {
        setListError(
          `Warning: ${allSkipped.length} duplicate image${
            allSkipped.length === 1 ? '' : 's'
          } were not added because they are already linked: ${[
            ...new Set(allSkipped),
          ].join(', ')}.`
        );
      } else {
        setListError(null);
      }
    } catch (err) {
      setFileError(err instanceof Error ? err.message : 'Gallery upload failed.');
    } finally {
      setUploading(false);
    }
  };

  const deleteOrphanedAssets = async (assetKeys: string[]) => {
    if (!institutionId || assetKeys.length === 0) return;
    for (const key of assetKeys) {
      try {
        await apiFetch(`academia/institutions/${institutionId}/pictures/delete`, {
          method: 'POST',
          body: JSON.stringify(
            key.includes('/') && !key.startsWith('http')
              ? { storage_key: key }
              : { url: key }
          ),
        });
      } catch {
        // Reference already removed locally; storage cleanup is best-effort.
      }
    }
  };

  const unlinkPictureIndices = async (
    indices: number[],
    options?: {
      collegePictureOverrides?: string[];
      confirmTitle?: string;
      confirmMessage?: string;
      confirmLabel?: string;
      cancelLabel?: string;
    }
  ) => {
    if (indices.length === 0 && options?.collegePictureOverrides === undefined) return;
    const confirmed = await openConfirm({
      title: options?.confirmTitle || 'Unlink image?',
      message:
        options?.confirmMessage ||
        'Unlink this image from the selected entity?',
      confirmLabel: options?.confirmLabel || 'Yes',
      cancelLabel: options?.cancelLabel || 'No',
      variant: 'warning',
    });
    if (!confirmed) return;

    const orphaned = assetsBecomingUnreferenced(picturesRef.current, indices);
    const indexSet = new Set(indices);
    const next = picturesRef.current.filter((_, index) => !indexSet.has(index));
    const overrides = options?.collegePictureOverrides ?? [...collegeOverridesRef.current];
    collegeOverridesRef.current = new Set(overrides);
    setCollegeOverrides(new Set(overrides));
    skipNextDefaultsResetRef.current = true;
    replacePictures(next, overrides);
    if (onPersistPictures) {
      // Survive the post-persist draft hydrate without briefly re-inheriting images.
      skipNextDefaultsResetRef.current = true;
      void onPersistPictures(next, { collegePictureOverrides: overrides });
    }
    if (orphaned.length > 0) {
      setDeletingUrl(orphaned[0]);
      try {
        await deleteOrphanedAssets(orphaned);
      } finally {
        setDeletingUrl(null);
      }
    }
  };

  const removePicture = async (picture: WizardPictureItem, index: number) => {
    if (!institutionId) {
      setListError('Save the Institution step before removing gallery images.');
      return;
    }
    await unlinkPictureIndices([index], {
      confirmTitle: 'Unlink image?',
      confirmMessage: `Unlink "${pictureDisplayFileName(picture)}" from this entity? Storage is only deleted when no other entity still uses the same file.`,
    });
    if (previewPicture?.local_id && previewPicture.local_id === picture.local_id) {
      setPreviewPicture(null);
    }
  };

  const handleUnlinkPictureInScope = async (
    scope: WizardPicturesEntityScope,
    picture: WizardPictureItem,
    index: number
  ) => {
    if (scope.type === 'college') {
      const assetKey = pictureAssetKey(picture);
      let owned = getCollegeOwnedPictureIndices(picturesRef.current, scope.collegeLocalId, [
        index,
      ]);
      // Also drop any other college-owned clones of the same shared asset.
      if (assetKey) {
        const byAsset = picturesRef.current
          .map((item, itemIndex) => ({ item, itemIndex }))
          .filter(
            ({ item }) =>
              pictureScopeKey(item) === collegeScopeKey(scope.collegeLocalId) &&
              pictureAssetKey(item) === assetKey
          )
          .map(({ itemIndex }) => itemIndex);
        owned = [...new Set([...owned, ...byAsset])];
      }
      const overrides = collegeOverridesRef.current.has(scope.collegeLocalId)
        ? [...collegeOverridesRef.current]
        : [...collegeOverridesRef.current, scope.collegeLocalId];
      await unlinkPictureIndices(owned, {
        collegePictureOverrides: overrides,
        confirmTitle: 'Unlink college image?',
        confirmMessage: `Unlink this image from ${scope.collegeName}? The college will stop inheriting that university image. The university mapping stays intact.`,
      });
      return;
    }

    let indices = [index];
    indices = expandInstitutionPictureUnlinkIndices(
      picturesRef.current,
      indices,
      collegeOverridesRef.current
    );
    await unlinkPictureIndices(indices, {
      confirmTitle: 'Unlink university image?',
      confirmMessage: cascadeToColleges
        ? 'This will also unlink the image from all child colleges (except overridden ones). Continue?'
        : 'Unlink this image from the university?',
      confirmLabel: 'Yes',
      cancelLabel: 'No',
    });
  };

  const handleUnlinkAllInScope = async (scope: WizardPicturesEntityScope) => {
    if (scope.type === 'college') {
      // Strictly this college's owned rows only — never expand to university/other colleges.
      const owned = getCollegeOwnedPictureIndices(
        picturesRef.current,
        scope.collegeLocalId
      );
      const overrides = collegeOverridesRef.current.has(scope.collegeLocalId)
        ? [...collegeOverridesRef.current]
        : [...collegeOverridesRef.current, scope.collegeLocalId];
      if (owned.length === 0 && collegeOverridesRef.current.has(scope.collegeLocalId)) {
        return;
      }
      await unlinkPictureIndices(owned, {
        collegePictureOverrides: overrides,
        confirmTitle: 'Unlink all college images?',
        confirmMessage: `Remove linked images shown for ${scope.collegeName} only? Other colleges and university images stay in place.`,
      });
      return;
    }

    const institutionIndices = picturesRef.current
      .map((picture, index) => ({ picture, index }))
      .filter(({ picture }) => pictureScopeKey(picture) === institutionScopeKey())
      .map(({ index }) => index);
    if (institutionIndices.length === 0) return;
    const expanded = expandInstitutionPictureUnlinkIndices(
      picturesRef.current,
      institutionIndices,
      collegeOverrides
    );
    await unlinkPictureIndices(expanded, {
      confirmTitle: 'Unlink all university images?',
      confirmMessage: cascadeToColleges
        ? 'This will also clear linked images on all child colleges (except overridden ones). Continue?'
        : 'Remove all university gallery links?',
      confirmLabel: 'Yes',
      cancelLabel: 'No',
    });
  };

  const handleUnlinkAllEverywhere = async () => {
    const allIndices = picturesRef.current
      .map((picture, index) => ({ picture, index }))
      .filter(({ picture }) => Boolean(pictureAssetKey(picture)))
      .map(({ index }) => index);
    if (allIndices.length === 0) return;

    await unlinkPictureIndices(allIndices, {
      collegePictureOverrides: [],
      confirmTitle: 'Unlink all images?',
      confirmMessage: `Remove all ${allIndices.length} image link${
        allIndices.length === 1 ? '' : 's'
      } from the parent university and every college?`,
      confirmLabel: 'Yes',
      cancelLabel: 'No',
    });
    setCollegeOverrides(new Set());
    setSelectedUrls(new Set());
    setSelectedPictureKeys(new Set());
    setPreviewPicture(null);
    setPreviewGallery([]);
  };

  const togglePictureKeySelection = (selectionKey: string) => {
    setSelectedPictureKeys(previous => {
      const next = new Set(previous);
      if (next.has(selectionKey)) next.delete(selectionKey);
      else next.add(selectionKey);
      return next;
    });
  };

  const setScopePictureSelection = (
    _scope: WizardPicturesEntityScope,
    keys: string[],
    selected: boolean
  ) => {
    setSelectedPictureKeys(previous => {
      const next = new Set(previous);
      for (const key of keys) {
        if (selected) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  };

  const handleUnlinkSelectedInScope = async (scope: WizardPicturesEntityScope) => {
    const selected = picturesRef.current
      .map((picture, index) => ({ picture, index }))
      .filter(({ picture }) => selectedPictureKeys.has(pictureSelectionKey(picture)));

    const inScope = selected.filter(({ picture }) => {
      if (scope.type === 'institution') {
        return pictureScopeKey(picture) === institutionScopeKey();
      }
      return pictureScopeKey(picture) === collegeScopeKey(scope.collegeLocalId);
    });
    if (inScope.length === 0) return;

    if (scope.type === 'college') {
      const ownedIndices = getCollegeOwnedPictureIndices(
        picturesRef.current,
        scope.collegeLocalId,
        inScope.map(({ index }) => index)
      );
      // If inherited university rows were selected, drop matching college-owned
      // clones of those assets only — never university / other-college rows.
      const selectedAssetKeys = new Set(
        inScope
          .map(({ picture }) => pictureAssetKey(picture))
          .filter((key): key is string => Boolean(key))
      );
      const byAsset = picturesRef.current
        .map((picture, index) => ({ picture, index }))
        .filter(
          ({ picture }) =>
            pictureScopeKey(picture) === collegeScopeKey(scope.collegeLocalId) &&
            selectedAssetKeys.has(pictureAssetKey(picture))
        )
        .map(({ index }) => index);
      const indices = [...new Set([...ownedIndices, ...byAsset])];
      const overrides = collegeOverridesRef.current.has(scope.collegeLocalId)
        ? [...collegeOverridesRef.current]
        : [...collegeOverridesRef.current, scope.collegeLocalId];
      await unlinkPictureIndices(indices, {
        collegePictureOverrides: overrides,
        confirmTitle: 'Unlink selected images?',
        confirmMessage: `Unlink ${inScope.length} selected image${
          inScope.length === 1 ? '' : 's'
        } from ${scope.collegeName} only?`,
        confirmLabel: 'Unlink selected',
      });
    } else {
      let indices = inScope.map(({ index }) => index);
      indices = expandInstitutionPictureUnlinkIndices(
        picturesRef.current,
        indices,
        collegeOverridesRef.current
      );
      await unlinkPictureIndices(indices, {
        confirmTitle: 'Unlink selected images?',
        confirmMessage: cascadeToColleges
          ? `Unlink ${inScope.length} selected image${
              inScope.length === 1 ? '' : 's'
            }? This will also apply to all child colleges (except overridden ones). Continue?`
          : `Unlink ${inScope.length} selected image${
              inScope.length === 1 ? '' : 's'
            } from the university?`,
        confirmLabel: 'Yes',
        cancelLabel: 'No',
      });
    }
    setSelectedPictureKeys(previous => {
      const removed = new Set(inScope.map(({ picture }) => pictureSelectionKey(picture)));
      return new Set([...previous].filter(key => !removed.has(key)));
    });
  };

  const openPicturePreview = (
    picture: WizardPictureItem,
    scopePictures: WizardPictureItem[]
  ) => {
    setPreviewGallery(scopePictures.filter(item => Boolean(item.url?.trim())));
    setPreviewPicture(picture);
  };

  const handleToggleCollegeOverride = (collegeLocalId: string, enabled: boolean) => {
    if (enabled) {
      // Entering override: snapshot current university images into this college's
      // owned set so the college can diverge without losing what it already had.
      const overrides = collegeOverridesRef.current.has(collegeLocalId)
        ? [...collegeOverridesRef.current]
        : [...collegeOverridesRef.current, collegeLocalId];
      collegeOverridesRef.current = new Set(overrides);
      setCollegeOverrides(new Set(overrides));

      const college = scopedColleges.find(
        item => resolveCollegeLocalId(item) === collegeLocalId
      );
      if (!college) {
        replacePictures(picturesRef.current, overrides);
        return;
      }
      const institutionPictures = picturesRef.current.filter(
        item => pictureScopeKey(item) === institutionScopeKey()
      );
      const existingKeys = new Set(
        picturesRef.current
          .filter(item => pictureScopeKey(item) === collegeScopeKey(collegeLocalId))
          .map(pictureAssetKey)
          .filter(Boolean)
      );
      const toAdd = institutionPictures
        .map(picture => clonePictureForCollege(picture, college))
        .filter(picture => {
          const assetKey = pictureAssetKey(picture);
          return Boolean(assetKey) && !existingKeys.has(assetKey);
        });
      skipNextDefaultsResetRef.current = true;
      replacePictures(
        toAdd.length > 0 ? [...picturesRef.current, ...toAdd] : picturesRef.current,
        overrides
      );
      return;
    }

    // Leaving override: keep this college's existing owned images as-is and only
    // resume *future* university cascades. Do not backfill images that were
    // uploaded while override was on.
    const nextOverrides = new Set(collegeOverridesRef.current);
    nextOverrides.delete(collegeLocalId);
    collegeOverridesRef.current = nextOverrides;
    setCollegeOverrides(nextOverrides);
    skipNextDefaultsResetRef.current = true;
    replacePictures(picturesRef.current, [...nextOverrides]);
  };

  const handleRemoveCollegeTab = async (collegeLocalId: string) => {
    const college = scopedColleges.find(
      item => resolveCollegeLocalId(item) === collegeLocalId
    );
    const collegeName = college?.name || 'this school / college';
    const confirmed = await openConfirm({
      title: 'Close school / college tab?',
      message: [
        `Close and remove "${collegeName}"?`,
        '',
        'This permanently deletes Step 4 and Step 5 data for this school / college:',
        '',
        '• Step 4 (Intakes): Academic calendar templates and term dates for this school / college.',
        '• Step 5 (Gallery): Gallery images linked specifically to this school / college (university images stay).',
        '',
        'The school / college will also be removed from Schools & Colleges and Academics in this wizard draft.',
        '',
        'Saved intake calendars are deleted on the server immediately and cannot be undone from here.',
      ].join('\n'),
      confirmLabel: 'Delete data & close',
      variant: 'danger',
    });
    if (!confirmed) return;

    setListError(null);

    if (institutionId) {
      try {
        const hierarchy = await apiFetch<{
          root: {
            children?: Array<{
              entity_type: string;
              entity_id: number;
              name: string;
              children?: Array<{ entity_type: string; entity_id: number }>;
            }>;
          };
        }>(`academia/institutions/${institutionId}/intakes/hierarchy`);
        const normalize = (value: string | null | undefined) =>
          (value || '').trim().toLowerCase();
        const collegeNode = (hierarchy.root.children || []).find(
          node =>
            node.entity_type === 'college' &&
            normalize(node.name) === normalize(college?.name)
        );
        if (collegeNode?.entity_id) {
          const collegeRows = await apiFetch<Array<{ id: number }>>(
            `academia/institutions/${institutionId}/intakes/by-entity?entity_type=college&entity_id=${collegeNode.entity_id}`
          );
          for (const row of Array.isArray(collegeRows) ? collegeRows : []) {
            if (!row?.id) continue;
            await apiFetch(
              `academia/institutions/${institutionId}/intakes/${row.id}`,
              { method: 'DELETE' }
            );
          }
        }
      } catch (err) {
        setListError(
          err instanceof Error
            ? err.message
            : 'Failed to delete intake calendars for this school / college.'
        );
      }
    }

    const indices = picturesRef.current
      .map((picture, index) =>
        (picture.college_local_id || '').trim() === collegeLocalId ? index : -1
      )
      .filter(index => index >= 0);
    const orphaned = assetsBecomingUnreferenced(picturesRef.current, indices);
    const indexSet = new Set(indices);
    const next = picturesRef.current.filter((_, index) => !indexSet.has(index));
    const overrides = [...collegeOverridesRef.current].filter(id => id !== collegeLocalId);
    collegeOverridesRef.current = new Set(overrides);
    setCollegeOverrides(new Set(overrides));
    skipNextDefaultsResetRef.current = true;
    replacePictures(next, overrides);
    if (onPersistPictures) {
      skipNextDefaultsResetRef.current = true;
      await onPersistPictures(next, { collegePictureOverrides: overrides });
    }
    if (orphaned.length > 0) {
      setDeletingUrl(orphaned[0]);
      try {
        await deleteOrphanedAssets(orphaned);
      } finally {
        setDeletingUrl(null);
      }
    }

    onRemoveCollege?.(collegeLocalId);
    setActiveScopeKey(institutionScopeKey());
  };

  const handleCascadeChange = async (enabled: boolean) => {
    if (enabled && scopedColleges.length > 0) {
      const confirmed = await openConfirm({
        title: 'Cascade to all colleges?',
        message:
          'University uploads and unlink actions will also apply to all child colleges (except overridden ones). Continue?',
        confirmLabel: 'Yes',
        cancelLabel: 'No',
        variant: 'warning',
      });
      if (!confirmed) return;
    }

    setCascadeToColleges(enabled);
    if (!enabled || scopedColleges.length === 0) return;

    // Explicitly turning cascade on may backfill current university images onto
    // non-overridden colleges only.
    const next = ensureCascadeCollegePictureClones(
      picturesRef.current,
      scopedColleges,
      collegeOverridesRef.current
    );
    if (next !== picturesRef.current) {
      skipNextDefaultsResetRef.current = true;
      replacePictures(next);
    }
  };

  const togglePictureSelection = (url: string) => {
    setSelectedUrls(previous => {
      const next = new Set(previous);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  };

  const deleteSelectedPictures = async () => {
    if (!institutionId || selectedUrls.size === 0) return;
    const urls = [...selectedUrls];
    const indices = picturesRef.current
      .map((picture, index) => ({ picture, index }))
      .filter(({ picture }) => picture.url && urls.includes(picture.url.trim()))
      .map(({ index }) => index);
    await unlinkPictureIndices(indices, {
      confirmTitle: 'Unlink selected images?',
      confirmMessage: `Unlink ${urls.length} selected image${urls.length === 1 ? '' : 's'}? Shared Cloudflare files are deleted only when no references remain.`,
    });
    setSelectedUrls(new Set());
  };

  const renderUploadPanel = (scope: WizardPicturesEntityScope) => (
    <div
      className="space-y-4"
      onFocusCapture={() => setActiveScopeKey(scopeKey(scope))}
      onPointerDownCapture={() => setActiveScopeKey(scopeKey(scope))}
    >
      <SelectField
        label="Picture type"
        value={pictureType}
        onChange={value => {
          setPictureType(value as PictureType);
          clearSelection();
        }}
        options={[...TYPE_OPTIONS]}
      />
      <div>
        <label className="mb-1 block text-sm font-semibold text-text-main">Select images</label>
        <input
          ref={scopeKey(scope) === activeScopeKey ? fileInputRef : undefined}
          type="file"
          multiple
          accept={
            pictureType === 'logo'
              ? 'image/svg+xml,image/png'
              : pictureType === 'banner'
                ? 'image/webp,image/jpeg'
                : 'image/webp,image/jpeg'
          }
          disabled={uploading}
          onChange={event => void handleFileSelection(event.target.files, scope)}
          className={wizardInputClass(Boolean(fileError))}
        />
        <p className="mt-1 text-xs text-text-muted">
          Select up to 20 images. Every file must be under 500 KB.
        </p>
        <WizardFieldError message={fileError || undefined} />
      </div>
      {selectedImages.length && scopeKey(scope) === activeScopeKey ? (
        <div className="space-y-2 rounded-xl border border-border-subtle bg-surface-bg p-3">
          {selectedImages.map(({ file, warnings }) => (
            <div key={`${file.name}-${file.lastModified}`} className="text-sm">
              <p className="font-semibold text-text-main">
                {file.name} ({Math.round(file.size / 1024)} KB)
              </p>
              {warnings.map(warning => (
                <p key={warning} className="text-xs text-amber-700">
                  {warning}
                </p>
              ))}
            </div>
          ))}
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              disabled={uploading}
              onClick={() => void uploadSelectedImages(scope)}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
            >
              <Upload size={15} />
              {uploading
                ? 'Uploading...'
                : `Upload ${selectedImages.length} image${selectedImages.length === 1 ? '' : 's'}`}
            </button>
            <button
              type="button"
              disabled={uploading}
              onClick={clearSelection}
              className="inline-flex items-center gap-1 rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted disabled:opacity-50"
            >
              <X size={15} /> Clear
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );

  const previewableImages = useMemo(() => {
    if (!previewPicture) return [];
    return (previewGallery.length > 0 ? previewGallery : pictures).filter(picture =>
      Boolean(picture.url?.trim())
    );
  }, [pictures, previewGallery, previewPicture]);

  const previewPositionLabel = useMemo(() => {
    if (!previewPicture || previewableImages.length === 0) return null;
    const index = previewableImages.findIndex(
      picture =>
        (previewPicture.local_id && picture.local_id === previewPicture.local_id) ||
        pictureSelectionKey(picture) === pictureSelectionKey(previewPicture) ||
        picture.url?.trim() === previewPicture.url?.trim()
    );
    return `${Math.max(index, 0) + 1} of ${previewableImages.length}`;
  }, [previewPicture, previewableImages]);

  return (
    <div className="space-y-6">
      {isHierarchy ? (
        <section className="rounded-2xl border border-border-subtle bg-card p-5">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className={wizardSectionTitleClass}>University & college gallery</h3>
              <p className="mt-1 text-sm text-text-muted">
                Upload at the university, cascade shared image references to colleges, then unlink or
                override per college without re-uploading.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setShowImageRequirements(true)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-border-subtle px-3 py-1.5 text-sm font-semibold text-text-main hover:bg-surface-bg"
              >
                <CircleHelp size={15} className="text-accent" />
                Image instructions
              </button>
              {pictures.length > 0 ? (
                <button
                  type="button"
                  disabled={uploading || deletingUrl !== null}
                  onClick={() => void handleUnlinkAllEverywhere()}
                  className="inline-flex items-center gap-1 rounded-xl border border-alert/30 px-3 py-1.5 text-sm font-semibold text-alert hover:bg-alert/10 disabled:opacity-50"
                >
                  <Unlink size={14} />
                  Unlink all
                </button>
              ) : null}
            </div>
          </div>
          {listError ? (
            <p className="mb-3 rounded-xl border border-alert/40 bg-alert/5 px-3 py-2 text-sm text-alert">
              {listError}
            </p>
          ) : null}
          <WizardPicturesHierarchyTree
            institutionName={institutionName}
            colleges={scopedColleges}
            pictures={pictures}
            collegeOverrides={collegeOverrides}
            cascadeToColleges={cascadeToColleges}
            activeScopeKey={activeScopeKey}
            selectedKeys={selectedPictureKeys}
            deletingKey={deletingUrl}
            uploading={uploading}
            onActiveScopeChange={setActiveScopeKey}
            onCascadeChange={enabled => void handleCascadeChange(enabled)}
            onToggleCollegeOverride={handleToggleCollegeOverride}
            onTogglePictureSelection={togglePictureKeySelection}
            onSetScopeSelection={setScopePictureSelection}
            onUnlinkPicture={(scope, picture, index) =>
              void handleUnlinkPictureInScope(scope, picture, index)
            }
            onUnlinkSelectedInScope={scope => void handleUnlinkSelectedInScope(scope)}
            onUnlinkAllInScope={scope => void handleUnlinkAllInScope(scope)}
            onViewPicture={openPicturePreview}
            renderUploadPanel={renderUploadPanel}
            onRemoveCollegeTab={
              onRemoveCollege ? collegeLocalId => void handleRemoveCollegeTab(collegeLocalId) : undefined
            }
          />
        </section>
      ) : (
        <>
      <section className={wizardSectionClass}>
        <h3 className={wizardSectionTitleClass}>Gallery upload</h3>
        <div className="grid grid-cols-1 gap-4">
          {renderUploadPanel({ type: 'institution' })}
        </div>
      </section>

      <section className="rounded-2xl border border-border-subtle bg-card p-5">
        <h3 className={wizardSectionTitleClass}>Gallery</h3>
        {listError ? (
          <p className="mb-3 rounded-xl border border-alert/40 bg-alert/5 px-3 py-2 text-sm text-alert">
            {listError}
          </p>
        ) : null}
        {pictures.length === 0 ? (
          <EmptyListMessage
            message={
              <span className="inline-flex items-center justify-center gap-2">
                <ImagePlus size={17} /> No images uploaded yet.
              </span>
            }
          />
        ) : (
          <>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border-subtle bg-surface-bg/50 px-3 py-2">
              <label className="inline-flex items-center gap-2 text-sm font-medium text-text-main">
                <input
                  type="checkbox"
                  checked={
                    pictures.filter(picture => Boolean(picture.url?.trim())).length > 0 &&
                    selectedUrls.size ===
                      pictures.filter(picture => Boolean(picture.url?.trim())).length
                  }
                  onChange={event => {
                    setSelectedUrls(
                      event.target.checked
                        ? new Set(
                            pictures
                              .map(picture => picture.url?.trim())
                              .filter((url): url is string => Boolean(url))
                          )
                        : new Set()
                    );
                  }}
                />
                Select all
                {selectedUrls.size > 0 ? ` (${selectedUrls.size})` : ''}
              </label>
              <button
                type="button"
                disabled={selectedUrls.size === 0 || deletingUrl !== null || uploading}
                onClick={() => void deleteSelectedPictures()}
                className="inline-flex items-center gap-1 rounded-lg bg-alert px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
              >
                <Trash2 size={14} />
                {deletingUrl === '__bulk__' ? 'Deleting...' : 'Unlink selected'}
              </button>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {pictures.map((picture, index) => {
                const url = picture.url?.trim() || '';
                const imageSrc = rewriteStoredMediaUrl(picture.url) || picture.url || '';
                return (
                  <article
                    key={picture.local_id || `${picture.url}-${index}`}
                    className={`relative overflow-hidden rounded-xl border ${
                      url && selectedUrls.has(url)
                        ? 'border-accent ring-2 ring-accent/20'
                        : 'border-border-subtle'
                    }`}
                  >
                    {url ? (
                      <label
                        className="absolute left-2 top-2 z-10 flex cursor-pointer rounded-md bg-card/90 p-1 shadow"
                        title="Select image"
                      >
                        <input
                          type="checkbox"
                          checked={selectedUrls.has(url)}
                          onChange={() => togglePictureSelection(url)}
                          aria-label={`Select ${pictureDisplayFileName(picture)}`}
                        />
                      </label>
                    ) : null}
                    {picture.url ? (
                      <button
                        type="button"
                        onClick={() =>
                          openPicturePreview(
                            picture,
                            pictures.filter(item => Boolean(item.url?.trim()))
                          )
                        }
                        className="group relative block h-36 w-full bg-surface-bg"
                        aria-label={`View ${pictureDisplayFileName(picture)} at original size`}
                      >
                        <img
                          src={imageSrc}
                          alt={pictureDisplayFileName(picture)}
                          className="h-36 w-full object-contain p-3"
                        />
                        <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-md bg-slate-900/75 px-2 py-1 text-xs font-semibold text-white opacity-0 transition-opacity group-hover:opacity-100">
                          <Maximize2 size={12} /> View
                        </span>
                      </button>
                    ) : null}
                <div className="flex items-start justify-between gap-2 p-3">
                  <div className="min-w-0 flex-1">
                    <p
                      className="break-all text-sm font-semibold leading-snug text-text-main"
                      title={pictureDisplayFileName(picture)}
                    >
                      {pictureDisplayFileName(picture)}
                    </p>
                    <p className="mt-0.5 text-xs text-text-muted">
                      {typeLabel(picture.picture_type)}
                      {picture.file_size ? ` · ${Math.round(picture.file_size / 1024)} KB` : ''}
                    </p>
                  </div>
                  <button
                    type="button"
                    aria-label={`Remove ${pictureDisplayFileName(picture)}`}
                    disabled={uploading || deletingUrl !== null}
                    onClick={() => void removePicture(picture, index)}
                    className="rounded-lg p-2 text-alert hover:bg-alert/10 disabled:opacity-50"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                  </article>
                );
              })}
            </div>
          </>
        )}
      </section>
        </>
      )}

      {previewPicture?.url ? (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 p-4"
          role="dialog"
          aria-modal="true"
          aria-label={`Preview ${pictureDisplayFileName(previewPicture)}${
            previewPositionLabel ? ` (${previewPositionLabel})` : ''
          }`}
          onClick={() => {
            setPreviewPicture(null);
            setPreviewGallery([]);
          }}
        >
          <div
            className="flex max-h-[95vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-card shadow-2xl"
            onClick={event => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-border-subtle px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                  File name
                </p>
                <p className="mt-0.5 break-all text-sm font-semibold leading-snug text-text-main sm:text-base">
                  {pictureDisplayFileName(previewPicture)}
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  Format:{' '}
                  {(() => {
                    const mime = (previewPicture.file_type || '').trim().toLowerCase();
                    if (mime.startsWith('image/')) {
                      return mime.slice('image/'.length).replace('jpeg', 'jpg').toUpperCase();
                    }
                    const name = pictureDisplayFileName(previewPicture);
                    const dot = name.lastIndexOf('.');
                    if (dot > 0 && dot < name.length - 1) {
                      return name.slice(dot + 1).toUpperCase();
                    }
                    return mime || '—';
                  })()}
                  {previewPicture.file_type ? ` (${previewPicture.file_type})` : ''}
                  {' · '}
                  {typeLabel(previewPicture.picture_type)}
                  {previewPicture.file_size
                    ? ` · ${Math.round(previewPicture.file_size / 1024)} KB`
                    : ''}
                  {previewPositionLabel ? ` · ${previewPositionLabel}` : ''}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                {previewPositionLabel ? (
                  <span className="rounded-lg bg-surface-bg px-2.5 py-1 text-sm font-semibold text-text-main">
                    {previewPositionLabel}
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={() => {
                    setPreviewPicture(null);
                    setPreviewGallery([]);
                  }}
                  className="rounded-lg p-2 text-text-muted hover:bg-surface-bg"
                  aria-label="Close image preview"
                >
                  <X size={20} />
                </button>
              </div>
            </div>
            <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-auto bg-slate-950 p-4">
              {previewableImages.length > 1 ? (
                <>
                  <button
                    type="button"
                    onClick={() => movePreview(-1)}
                    className="absolute left-3 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/65 p-3 text-white shadow-lg transition hover:bg-black/85"
                    aria-label="View previous image"
                    title="Previous image"
                  >
                    <ChevronLeft size={30} />
                  </button>
                  <button
                    type="button"
                    onClick={() => movePreview(1)}
                    className="absolute right-3 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/65 p-3 text-white shadow-lg transition hover:bg-black/85"
                    aria-label="View next image"
                    title="Next image"
                  >
                    <ChevronRight size={30} />
                  </button>
                </>
              ) : null}
              <img
                src={rewriteStoredMediaUrl(previewPicture.url) || previewPicture.url}
                alt={pictureDisplayFileName(previewPicture)}
                className="max-h-[80vh] max-w-full object-contain"
              />
              {previewPositionLabel && previewableImages.length > 1 ? (
                <span className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/70 px-3 py-1 text-sm font-semibold text-white">
                  {previewPositionLabel}
                </span>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {showImageRequirements ? (
        <div
          className="fixed inset-0 z-[130] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          role="presentation"
          onClick={() => setShowImageRequirements(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="image-requirements-title"
            className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-2xl"
            onClick={event => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-border-subtle px-5 py-4">
              <div>
                <h3 id="image-requirements-title" className="text-lg font-bold text-text-main">
                  Image requirements
                </h3>
                <p className="mt-1 text-sm text-text-muted">
                  Follow these specs so logos, banners, and gallery images display correctly.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowImageRequirements(false)}
                className="rounded-lg p-1.5 text-text-muted hover:bg-surface-bg hover:text-text-main"
                aria-label="Close image instructions"
              >
                <X size={16} />
              </button>
            </div>
            <div className="space-y-4 overflow-y-auto p-5">
              <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
                <p className="font-semibold text-text-main">Logo</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-text-muted">
                  <li>Formats: SVG preferred; PNG secondary</li>
                  <li>Recommended width: 200–300px</li>
                </ul>
              </div>
              <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
                <p className="font-semibold text-text-main">Banner (Hero)</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-text-muted">
                  <li>Formats: WebP or JPEG</li>
                  <li>Width: 1800–2500px</li>
                  <li>Aspect ratio: 3:1 or 2:1</li>
                </ul>
              </div>
              <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
                <p className="font-semibold text-text-main">Gallery</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-text-muted">
                  <li>Formats: WebP or JPEG</li>
                  <li>Minimum width: 1200px</li>
                  <li>Keep a consistent 3:2, 4:3, or 1:1 ratio</li>
                </ul>
              </div>
              <p className="text-xs text-text-muted">
                Files are stored once in Cloudflare R2. Cascading to colleges creates reference links to
                the same <code className="rounded bg-surface-bg px-1 py-0.5">storage_key</code> — no
                duplicate uploads.
              </p>
            </div>
            <div className="flex justify-end border-t border-border-subtle px-5 py-3">
              <button
                type="button"
                onClick={() => setShowImageRequirements(false)}
                className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
});

InstitutionWizardStep6.displayName = 'InstitutionWizardStep6';
export default InstitutionWizardStep6;
