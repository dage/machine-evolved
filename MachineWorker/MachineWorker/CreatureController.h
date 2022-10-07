#pragma once

#include <math.h>

#include "CoreMinimal.h"
#include "Engine/LevelScriptActor.h"
#include "Engine/World.h"

#include "Types/SlateEnums.h"

#include "Blueprint/UserWidget.h"
#include "TextWidgetTypes.h"
#include "Button.h"
#include "TextBlock.h"
#include "ComboBoxString.h"
#include "CheckBox.h"

#include "BulletInterface.h"
#include "BulletCreature.h"
#include "CreatureStructure.h"
#include "AsyncCommunicator.h"
#include "IMotorController.h"
#include "LinearMotorController.h"
#include "UnrealCreature.h"
#include "Creature.h"
#include "WorkEvaluator.h"
#include "BulletWorker.h"

#include "CreatureController.generated.h"

/**
 * Controls the creatures and ties everything together. Must be set as the base level class in the UE editor.
 */
UCLASS()
class MACHINEWORKER_API ACreatureController : public ALevelScriptActor
{
	GENERATED_BODY()

public:
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = Materials)
	UMaterial* capsuleMaterial;

	/** Remove the current menu widget and create a new one from the specified class, if provided. */
	UFUNCTION(BlueprintCallable, Category = "Menu")
	void SetMenuWidget(TSubclassOf<UUserWidget> NewWidgetClass);

	UFUNCTION()
	void onSpawnBestClicked();

	UFUNCTION()
	void onNumThreadsChanged(FString sItem, ESelectInfo::Type seltype);

	UFUNCTION()
	void onDoRenderChanged(bool isChecked);
	
protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void Tick(float DeltaSeconds) override;	

	/** Reference to the UI widget layer on top set in the UE4 editor in Level Blueprint properties */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Menu")
	TSubclassOf<UUserWidget> StartingWidgetClass;

private:
	const FText SPAWN_BEST_BUTTON_CAPTION = FText::FromString(FString(UTF8_TO_TCHAR("Spawn best")));
	const FText KILL_SPAWNED_BEST_BUTTON_CAPTION = FText::FromString(FString(UTF8_TO_TCHAR("Kill")));
	bool isBestSpawned = false;

	//AsyncCommunicator* communicator;
	Communicator* communicator = new Communicator();

	WorkEvaluator bestCreatureEvaluator = WorkEvaluator();
	BulletInterface bullet;		// Instance that runs rendered creatures inside the game main thread

	std::stack<BulletWorker*> workers = std::stack<BulletWorker*>();
	void setNumWorkers(int num);

	UTextBlock* serverStatusWidget;
	UButton* spawnBestWidget;
	UTextBlock* spawnBestTextWidget;
	UComboBoxString* numThreadsWidget;
	UCheckBox* doRenderWidget;

	double uiUpdateTimeStamp = FPlatformTime::Seconds();

	void spawnBestCreature();
	void killBestCreature();
	Creature* previewCreature = nullptr;
};
